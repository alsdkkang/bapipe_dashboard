"""Outbound email notifications for the bapipe dashboard.

Currently sends via Gmail SMTP. The single public entry point is
``send_approval_email`` — to switch to a transactional email API later (Resend,
SendGrid, …), replace only the transport inside this module; callers don't change.

Configuration lives in Streamlit secrets under an ``[email]`` section::

    [email]
    sender = "you@gmail.com"
    app_password = "abcd efgh ijkl mnop"   # Gmail App Password (needs 2FA)
    app_url = "https://your-app.streamlit.app"   # optional, linked in the email

With no ``[email]`` section everything here is a no-op, so approvals keep working
without any email configured.
"""
import smtplib
import ssl
from email.message import EmailMessage

import streamlit as st


def _email_config():
    try:
        cfg = st.secrets["email"]
        return dict(cfg)
    except Exception:
        return None


def email_enabled() -> bool:
    cfg = _email_config()
    return bool(cfg and cfg.get("sender") and cfg.get("app_password"))


def send_approval_email(to_email, to_name=""):
    """Notify a newly-approved user that they can log in.

    Returns ``(ok: bool, info: str)``. Never raises — a failure returns
    ``(False, reason)`` so the caller can approve regardless of email working.
    """
    cfg = _email_config()
    if not cfg or not cfg.get("sender") or not cfg.get("app_password"):
        return False, "email not configured"

    sender = cfg["sender"]
    app_url = cfg.get("app_url", "")
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Your account ({to_email}) has been approved for the Animal Behaviour "
        f"Analysis dashboard. You can now log in"
        + (f" at {app_url}" if app_url else "")
        + ".\n\n— Abizaid Lab"
    )
    msg = EmailMessage()
    msg["Subject"] = "Your access has been approved"
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls(context=ctx)
            server.login(sender, cfg["app_password"])
            server.send_message(msg)
        return True, "sent"
    except Exception as e:  # deliberately broad: email must never break approval
        return False, f"{type(e).__name__}: {e}"
