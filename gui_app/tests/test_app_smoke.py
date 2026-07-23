import os
import sys
from pathlib import Path

import pytest

GUI_APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI_APP))
sys.path.insert(0, str(GUI_APP.parent / "src"))  # so `import bapipe` works in tests
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


def test_no_stray_blue_in_app_source():
    src = (GUI_APP / "app.py").read_text()
    assert "#2f6df0" not in src, "stray blue should be replaced by a token"


def test_admin_sees_pending_approvals(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    monkeypatch.setenv("BAPIPE_ACCESS_FILE", str(tmp_path / "access.json"))
    monkeypatch.setenv("BAPIPE_USERS_FILE", str(tmp_path / "users.json"))
    import auth
    import importlib
    importlib.reload(auth)
    # An admin is signed in (via _fresh_apptest) and one user is awaiting approval.
    auth._save_access({"admins": ["tester@example.com"], "approved": [],
                       "pending": {"newbie@example.com": "Newbie"}})
    at = _fresh_apptest()
    at.session_state["phase"] = "records"
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert any("Approve" in l for l in labels), "admin approvals UI not rendered"
    texts = [m.value for m in at.markdown]
    assert any("newbie@example.com" in (t or "") for t in texts), "pending user not shown"


def _apptest_with_sample_loaded():
    """AppTest with the bundled sample loaded (run through the loading phase).
    Returns None if the sample isn't bundled (callers should skip)."""
    import samples
    import importlib
    importlib.reload(samples)
    if not samples.sample_available():
        return None
    at = _fresh_apptest()
    at.session_state["data_video_dir"] = str(samples.SAMPLE_DIR / "videos")
    at.session_state["data_dlc_dir"] = str(samples.SAMPLE_DIR / "mouse_labels")
    at.session_state["data_landmark_dir"] = str(samples.SAMPLE_DIR / "landmark_labels")
    at.session_state["data_calib_path"] = str(samples.SAMPLE_DIR / "camera_calibrations.json")
    at.session_state["data_meta_path"] = str(samples.SAMPLE_DIR / "metadata.csv")
    at.session_state["data_join_col"] = "id"
    at.session_state["pending_load_ids"] = list(samples.SAMPLE_IDS)
    at.session_state["phase"] = "loading"
    at.run()
    return at


def test_load_sample_populates_video_set(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    at = _apptest_with_sample_loaded()
    if at is None:
        import pytest
        pytest.skip("sample_data not bundled")
    assert not at.exception
    assert "video_set" in at.session_state
    assert list(at.session_state["video_set"].index) == ["f1", "f2", "f3", "f4"]


def test_app_phase_has_left_nav(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    at = _apptest_with_sample_loaded()
    if at is None:
        import pytest
        pytest.skip("sample_data not bundled")
    at.session_state["phase"] = "app"
    at.run()
    assert not at.exception
    opts = [o for r in at.radio for o in r.options]
    assert "Overview" in opts and "Distance" in opts


def test_overview_shows_kpi_tiles(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    at = _apptest_with_sample_loaded()
    if at is None:
        import pytest
        pytest.skip("sample_data not bundled")
    at.session_state["phase"] = "app"
    at.session_state["app_view"] = "Overview"
    at.run()
    assert not at.exception
    md = [m.value for m in at.markdown]
    assert any("Animals" in (t or "") for t in md)
    assert any("Groups" in (t or "") for t in md)


def test_annotate_clip_clamps_to_video_length(tmp_path):
    import samples
    import importlib
    importlib.reload(samples)
    if not samples.sample_available():
        import pytest
        pytest.skip("sample_data not bundled")
    import pandas as pd
    import bapipe
    import analysis
    df = pd.read_csv(samples.SAMPLE_DIR / "bapipe_datafiles.csv")
    df = df[df["id"] == "f1"].reset_index(drop=True)
    cfg = bapipe.AnalysisConfig(pcutoff=0.6, use_box_reference=True,
                                remove_lens_distortion=True, box_shape=(400, 300))
    vs = bapipe.VideoSet.load(df, cfg, root_dir=str(samples.SAMPLE_DIR),
                              use_multiprocessing=False)
    v = vs[0]
    out = tmp_path / "clip.mp4"
    # Start near the end with a length that overshoots the trimmed video: must
    # clamp instead of reading empty frames (the OpenCV cvtColor crash).
    analysis.annotate_clip(v, max(0, v.frame_count - 10), 100, out)
    assert out.exists() and out.stat().st_size > 0


def test_records_dashboard_lists_seeded_record(tmp_path, monkeypatch):
    monkeypatch.setenv("BAPIPE_RECORDS_DIR", str(tmp_path))
    import records as recmod
    import importlib
    importlib.reload(recmod)
    recmod.add_record("tester@example.com", {
        "name": "seeded run", "animals": ["m1"],
        "config": {"box_shape": [400, 300]},
        "results": {"per_animal": [{"id": "m1", "distance": 1.0}], "group_summary": []},
    })
    at = _fresh_apptest()
    at.session_state["phase"] = "records"
    at.run()
    assert not at.exception
    assert any("seeded run" in (m.value or "") for m in at.markdown)
