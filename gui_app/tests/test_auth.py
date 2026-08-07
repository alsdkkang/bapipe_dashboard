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


def test_state_files_follow_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BAPIPE_USERS_FILE", str(tmp_path / "u.json"))
    monkeypatch.setenv("BAPIPE_ACCESS_FILE", str(tmp_path / "a.json"))
    import auth
    importlib.reload(auth)
    assert auth._users_file() == tmp_path / "u.json"
    assert auth._access_file() == tmp_path / "a.json"
    # register writes to the env path and creates the parent dir
    assert auth.register("New@x.com", "New", "secret1") is None
    assert (tmp_path / "u.json").exists()
    assert auth.verify("new@x.com", "secret1") is True


def test_admins_and_enablement_from_env(monkeypatch):
    monkeypatch.setenv("BAPIPE_ADMINS", "Boss@x.com, two@x.com ")
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: None)  # no secrets.toml
    assert auth._seed_admins() == ["boss@x.com", "two@x.com"]
    assert auth.auth_enabled() is True
    assert auth.is_admin("BOSS@x.com") is True


def test_bootstrap_admins_seeds_login_from_password(monkeypatch, tmp_path):
    monkeypatch.setenv("BAPIPE_USERS_FILE", str(tmp_path / "u.json"))
    monkeypatch.setenv("BAPIPE_ACCESS_FILE", str(tmp_path / "a.json"))
    monkeypatch.setenv("BAPIPE_ADMINS", "boss@x.com")
    monkeypatch.setenv("BAPIPE_ADMIN_PASSWORD", "pw-test-1")
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: None)  # no secrets.toml
    assert auth.verify("boss@x.com", "pw-test-1") is False  # no account yet
    auth.bootstrap_admins()
    assert auth.verify("boss@x.com", "pw-test-1") is True    # seeded, can log in
    assert auth.verify("boss@x.com", "wrong") is False
    # a self-chosen password is not clobbered by a re-run
    import bcrypt
    users = auth._load_users()
    users["boss@x.com"]["password"] = bcrypt.hashpw(b"mine", bcrypt.gensalt()).decode()
    auth._save_users(users)
    auth.bootstrap_admins()
    assert auth.verify("boss@x.com", "mine") is True


def test_bootstrap_noop_without_password(monkeypatch, tmp_path):
    monkeypatch.setenv("BAPIPE_USERS_FILE", str(tmp_path / "u.json"))
    monkeypatch.setenv("BAPIPE_ADMINS", "boss@x.com")
    monkeypatch.delenv("BAPIPE_ADMIN_PASSWORD", raising=False)
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: None)
    auth.bootstrap_admins()
    assert auth.verify("boss@x.com", "anything") is False  # nothing seeded


def test_google_disabled_even_with_auth_secret(monkeypatch):
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: {"x": 1} if section == "auth" else None)
    assert auth.google_enabled() is False
