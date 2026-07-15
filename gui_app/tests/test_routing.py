import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import routing  # noqa: E402


def test_explicit_session_phase_wins():
    assert routing.resolve_phase(False, "wizard") == "wizard"
    assert routing.resolve_phase(True, "guide") == "guide"


def test_first_time_user_sees_welcome():
    assert routing.resolve_phase(False, None) == "welcome"


def test_returning_user_sees_records():
    assert routing.resolve_phase(True, None) == "records"


def test_unknown_session_phase_falls_back():
    assert routing.resolve_phase(True, "bogus") == "records"
    assert routing.resolve_phase(False, "bogus") == "welcome"
