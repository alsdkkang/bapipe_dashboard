import importlib
import sys
from pathlib import Path

import pytest

# Make `import records` resolve to gui_app/records.py
GUI_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_APP))


@pytest.fixture()
def records(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    import records as mod
    importlib.reload(mod)
    return mod


def _rec(name="run", animals=("m1", "m2"), box=(400, 300)):
    return {
        "name": name,
        "animals": list(animals),
        "config": {"box_shape": list(box), "use_box_reference": True},
        "results": {"per_animal": [], "group_summary": []},
    }


def test_user_key_defaults_to_local(records):
    assert records.user_key(None) == "local"
    assert records.user_key("") == "local"
    assert records.user_key("A.B@Example.com") == records.user_key("a.b@example.com")


def test_onboarded_roundtrip(records):
    assert records.is_onboarded("u@x.com") is False
    records.mark_onboarded("u@x.com")
    assert records.is_onboarded("u@x.com") is True


def test_add_and_list_newest_first(records):
    a = records.add_record("u@x.com", _rec(name="first"))
    b = records.add_record("u@x.com", _rec(name="second", animals=("m3",)))
    assert "id" in a and "created" in a
    names = [r["name"] for r in records.list_records("u@x.com")]
    assert names == ["second", "first"]


def test_add_dedupe_same_animals_and_config_updates_timestamp(records):
    a = records.add_record("u@x.com", _rec())
    b = records.add_record("u@x.com", _rec())  # identical animals + config
    assert len(records.list_records("u@x.com")) == 1
    assert b["id"] == a["id"]


def test_get_and_delete(records):
    a = records.add_record("u@x.com", _rec())
    assert records.get_record("u@x.com", a["id"])["name"] == "run"
    records.delete_record("u@x.com", a["id"])
    assert records.get_record("u@x.com", a["id"]) is None


def test_users_are_isolated(records):
    records.add_record("u1@x.com", _rec())
    assert records.list_records("u2@x.com") == []


def test_assemble_record_is_json_serialisable(records):
    import json as _json
    import pandas as pd
    per = pd.DataFrame(
        {"distance": [27000.0], "time_in_zone": [12.0], "duration_s": [650.0]},
        index=pd.Index(["m1"], name="id"),
    )
    summ = pd.DataFrame({"distance": [27000.0]}, index=pd.Index(["saline"], name="group"))
    rec = records.assemble_record(
        name="run", animals=["m1"],
        config={"box_shape": (400, 300)}, per_animal=per, group_summary=summ,
    )
    # must round-trip through JSON without error
    _json.dumps(rec)
    assert rec["name"] == "run"
    assert rec["animals"] == ["m1"]
    assert rec["config"]["box_shape"] == [400, 300]
    assert rec["results"]["per_animal"][0]["id"] == "m1"
    assert rec["results"]["group_summary"][0]["group"] == "saline"
