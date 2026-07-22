import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_send_disabled_when_unconfigured(monkeypatch):
    import notifications
    import importlib
    importlib.reload(notifications)
    monkeypatch.setattr(notifications, "_email_config", lambda: None)
    ok, info = notifications.send_approval_email("x@y.com", "X")
    assert ok is False
    assert "not configured" in info
    assert notifications.email_enabled() is False


def test_send_uses_smtp_when_configured(monkeypatch):
    import notifications
    import importlib
    importlib.reload(notifications)
    monkeypatch.setattr(notifications, "_email_config",
                        lambda: {"sender": "admin@gmail.com", "app_password": "pw",
                                 "app_url": "https://app.example"})
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, user, pw):
            sent["login"] = (user, pw)

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    ok, info = notifications.send_approval_email("new@user.com", "New")
    assert ok is True
    assert sent["host"] == "smtp.gmail.com" and sent["port"] == 587
    assert sent["tls"] is True
    assert sent["login"] == ("admin@gmail.com", "pw")
    assert sent["msg"]["To"] == "new@user.com"
    assert sent["msg"]["From"] == "admin@gmail.com"
    body = sent["msg"].get_content().lower()
    assert "approved" in body and "https://app.example" in body
