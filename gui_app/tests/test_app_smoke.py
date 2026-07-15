import os
import sys
from pathlib import Path

import pytest

GUI_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_APP))
APP = str(GUI_APP / "app.py")


@pytest.fixture(autouse=True)
def _tmp_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))


def _fresh_apptest():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=30)
    # Auth is enabled via .streamlit/secrets.toml; sign a test admin in so the
    # login gate passes and the phase router runs.
    at.secrets["access"] = {"admins": ["tester@example.com"]}
    at.session_state["auth_email"] = "tester@example.com"
    at.session_state["auth_name"] = "Tester"
    return at


def test_first_time_user_sees_welcome():
    at = _fresh_apptest().run()
    assert not at.exception
    texts = [m.value for m in at.markdown]
    assert any("bapipe" in t for t in texts)
    labels = [b.label for b in at.button]
    assert any("Start" in l for l in labels)
    assert any("guide" in l.lower() for l in labels)


def test_returning_user_sees_records_phase():
    at = _fresh_apptest()
    at.session_state["phase"] = "records"
    at.run()
    assert not at.exception


def test_wizard_renders_step_zero():
    at = _fresh_apptest()
    at.session_state["phase"] = "wizard"
    at.run()
    assert not at.exception
    texts = [m.value for m in at.markdown] + [m.value for m in at.subheader]
    assert any("experiment" in (t or "").lower() for t in texts)


def test_app_phase_without_data_redirects():
    at = _fresh_apptest()
    at.session_state["phase"] = "app"
    at.run()
    assert not at.exception
