import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_is_admin_reads_access(monkeypatch):
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_load_access",
                        lambda: {"admins": ["boss@x.com"], "approved": [], "pending": {}})
    assert auth.is_admin("boss@x.com") is True
    assert auth.is_admin("BOSS@x.com") is True   # case-insensitive
    assert auth.is_admin("nobody@x.com") is False
    assert auth.is_admin(None) is False
