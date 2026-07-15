"""Per-user record store for the bapipe dashboard.

Stores small analysis-result snapshots (numbers + metadata only — never raw
video/pose data) as one JSON file per user under `gui_app/records/`. Keyed by
the signed-in email; falls back to "local" when auth is disabled. UI-level
privacy: only the owning user's file is ever read/written here, and no admin
path lists another user's records.

The store directory is overridable via the BAPIPE_RECORDS_DIR env var (tests).
"""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def store_dir() -> Path:
    d = Path(os.environ.get("BAPIPE_RECORDS_DIR", str(HERE / "records")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_key(email) -> str:
    email = (email or "").strip().lower()
    if not email:
        return "local"
    slug = re.sub(r"[^a-z0-9]+", "_", email).strip("_")
    h = hashlib.sha1(email.encode()).hexdigest()[:8]
    return f"{slug}_{h}" if slug else h


def _path(email) -> Path:
    return store_dir() / f"{user_key(email)}.json"


def _load(email) -> dict:
    p = _path(email)
    if p.exists():
        try:
            data = json.loads(p.read_text())
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("onboarded", False)
    data.setdefault("records", [])
    return data


def _save(email, data) -> None:
    _path(email).write_text(json.dumps(data, indent=2))


def is_onboarded(email) -> bool:
    return bool(_load(email)["onboarded"])


def mark_onboarded(email) -> None:
    data = _load(email)
    if not data["onboarded"]:
        data["onboarded"] = True
        _save(email, data)


def _signature(record) -> tuple:
    return (tuple(record.get("animals", [])),
            json.dumps(record.get("config", {}), sort_keys=True))


def list_records(email) -> list:
    # newest first
    return list(reversed(_load(email)["records"]))


def add_record(email, record) -> dict:
    """Append a record; if the most recent record has the same animals+config,
    refresh its timestamp instead of adding a duplicate."""
    data = _load(email)
    now = datetime.now().isoformat(timespec="seconds")
    if data["records"] and _signature(data["records"][-1]) == _signature(record):
        data["records"][-1]["created"] = now
        _save(email, data)
        return data["records"][-1]
    stored = dict(record)
    stored["id"] = uuid.uuid4().hex
    stored["created"] = now
    data["records"].append(stored)
    _save(email, data)
    return stored


def get_record(email, rid):
    for r in _load(email)["records"]:
        if r.get("id") == rid:
            return r
    return None


def delete_record(email, rid) -> None:
    data = _load(email)
    data["records"] = [r for r in data["records"] if r.get("id") != rid]
    _save(email, data)


def _jsonable(value):
    """Coerce numpy/tuple values into plain JSON types."""
    import numpy as np
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def assemble_record(name, animals, config, per_animal, group_summary):
    """Build a JSON-serialisable snapshot from computed result frames.

    `per_animal` is indexed by animal id; `group_summary` (optional) is indexed
    by group. Only numbers + metadata are stored — no raw video/pose data.
    """
    pa = per_animal.reset_index()
    pa = pa.rename(columns={pa.columns[0]: "id"})
    per_rows = [{k: _jsonable(v) for k, v in row.items()}
                for row in pa.to_dict(orient="records")]
    summ_rows = []
    if group_summary is not None and len(group_summary):
        gs = group_summary.reset_index()
        gs = gs.rename(columns={gs.columns[0]: "group"})
        gs.columns = ["_".join(map(str, c)).strip("_") if isinstance(c, tuple) else str(c)
                      for c in gs.columns]
        summ_rows = [{k: _jsonable(v) for k, v in row.items()}
                     for row in gs.to_dict(orient="records")]
    return {
        "name": name,
        "animals": [str(a) for a in animals],
        "config": _jsonable(config),
        "results": {"per_animal": per_rows, "group_summary": summ_rows},
    }
