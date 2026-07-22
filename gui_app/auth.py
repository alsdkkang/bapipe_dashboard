"""Login for the bapipe dashboard: email/password (bcrypt), gated by an
admin-approved allow-list. No Google/OIDC — Phase 1 demo is email/password only.

Auth is ENABLED when at least one admin is configured, either via the
`BAPIPE_ADMINS` env var (comma-separated emails) or `.streamlit/secrets.toml`'s
`[access]` section. With no admins configured, everything here is a no-op, so the
app keeps running locally without any credentials.

- **Email/password**: users self-register; new accounts are stored in the users
  state file (bcrypt-hashed, path from `BAPIPE_USERS_FILE`, default
  `gui_app/users.json`) and land in the pending list until an admin approves them.
  Login state is kept in `st.session_state` (a full browser refresh logs the user
  out).
- **Admins** (from `BAPIPE_ADMINS` and/or `secrets["access"]["admins"]`) are always
  allowed and approve others from the sidebar. Approvals live in the access state
  file (path from `BAPIPE_ACCESS_FILE`, default `gui_app/access.json`).
"""
import html
import json
import os
import re
from pathlib import Path

import bcrypt
import streamlit as st

import notifications

HERE = Path(__file__).resolve().parent
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _access_file() -> Path:
    return Path(os.environ.get("BAPIPE_ACCESS_FILE", str(HERE / "access.json")))


def _users_file() -> Path:
    return Path(os.environ.get("BAPIPE_USERS_FILE", str(HERE / "users.json")))


# --------------------------------------------------------------------------- #
# Config / enablement
# --------------------------------------------------------------------------- #
def _secret(section):
    try:
        return st.secrets[section]
    except Exception:
        return None


def auth_enabled():
    return bool(_seed_admins()) or _secret("access") is not None


def google_enabled():
    # Google/OIDC removed for the Phase 1 demo. Always disabled.
    return False


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _seed_admins():
    admins = []
    acc = _secret("access")
    try:
        admins += [e.strip().lower() for e in acc["admins"]]
    except Exception:
        pass
    env = os.environ.get("BAPIPE_ADMINS", "")
    admins += [e.strip().lower() for e in env.split(",") if e.strip()]
    return sorted(set(admins))


def _load_access():
    data = {"admins": [], "approved": [], "pending": {}}
    p = _access_file()
    if p.exists():
        try:
            data.update(json.loads(p.read_text()))
        except Exception:
            pass
    data["admins"] = sorted(set(data.get("admins", [])) | set(_seed_admins()))
    data.setdefault("approved", [])
    data.setdefault("pending", {})
    return data


def _save_access(data):
    p = _access_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _load_users():
    p = _users_file()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _save_users(users):
    p = _users_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(users, indent=2))


def _allowed(email):
    email = (email or "").lower()
    data = _load_access()
    return email in set(data["admins"]) | {a.lower() for a in data["approved"]}


def _mark_pending(email, name):
    email = (email or "").lower()
    data = _load_access()
    if email and not _allowed(email) and email not in data["pending"]:
        data["pending"][email] = name or ""
        _save_access(data)


# --------------------------------------------------------------------------- #
# Email/password
# --------------------------------------------------------------------------- #
def register(email, name, password):
    """Create a new email/password account (pending admin approval). Returns error str or None."""
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return "Enter a valid email address."
    if len(password or "") < 6:
        return "Password must be at least 6 characters."
    users = _load_users()
    if email in users:
        return "An account with this email already exists."
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email] = {"name": name.strip(), "password": pw_hash}
    _save_users(users)
    _mark_pending(email, name.strip())
    return None


def verify(email, password):
    email = (email or "").strip().lower()
    users = _load_users()
    rec = users.get(email)
    if not rec:
        return False
    try:
        return bcrypt.checkpw(password.encode(), rec["password"].encode())
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Current user
# --------------------------------------------------------------------------- #
def _current():
    """Return (email, name) of the signed-in user, or (None, None)."""
    email = st.session_state.get("auth_email")
    if email:
        return email, st.session_state.get("auth_name", "")
    return None, None


def current_user():
    """Public: (email, name) of the signed-in user, or (None, None)."""
    return _current()


def _logout():
    st.session_state.pop("auth_email", None)
    st.session_state.pop("auth_name", None)


# --------------------------------------------------------------------------- #
# Login page
# --------------------------------------------------------------------------- #
def _render_logo(logo_path, width=110):
    if logo_path and Path(logo_path).exists():
        if str(logo_path).endswith(".svg"):
            st.image(Path(logo_path).read_text(), width=width)
        else:
            st.image(str(logo_path), width=width)


def _login_page(logo_path):
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(
            "<div style='text-align:center;font-size:1.4rem;font-weight:700;"
            "color:var(--ink);letter-spacing:-0.02em;line-height:1.2;"
            "margin:0.2rem 0 1rem'>Animal Behaviour Analysis by Abizaid Lab</div>",
            unsafe_allow_html=True)
        mode = st.session_state.get("auth_mode", "login")

        if mode == "register":
            st.subheader("Sign up")
            with st.form("register_form"):
                name = st.text_input("Name")
                email = st.text_input("Email")
                pw = st.text_input("Password", type="password")
                pw2 = st.text_input("Confirm password", type="password")
                ok = st.form_submit_button("Sign up", type="primary")
            if ok:
                if pw != pw2:
                    st.error("Passwords do not match.")
                else:
                    err = register(email, name, pw)
                    if err:
                        st.error(err)
                    else:
                        st.success("Account created. An admin must approve it before you can log in.")
                        st.session_state["auth_mode"] = "login"
            if st.button("← Back to log in"):
                st.session_state["auth_mode"] = "login"
                st.rerun()
            return

        # login mode
        with st.form("login_form"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", type="primary")
        if ok:
            if verify(email, pw):
                st.session_state["auth_email"] = email.strip().lower()
                st.session_state["auth_name"] = _load_users().get(email.strip().lower(), {}).get("name", "")
                st.rerun()
            else:
                st.error("Incorrect email or password.")

        st.caption("Don't have an account?")
        if st.button("Sign up", use_container_width=True):
            st.session_state["auth_mode"] = "register"
            st.rerun()


def require_login(logo_path=None):
    """Gate the whole app: renders login / pending screens and stops when not permitted."""
    if not auth_enabled():
        return

    email, name = _current()
    if not email:
        _login_page(logo_path)
        st.stop()

    if not _allowed(email):
        _mark_pending(email, name)
        _, mid, _ = st.columns([1, 1.4, 1])
        with mid:
            st.title("Access pending")
            st.warning(f"Your account (**{email}**) is awaiting admin approval. "
                       "Contact the study admin, then reload this page.")
            st.button("Log out", on_click=_logout)
        st.stop()

    # allowed → clear any stale pending entry
    data = _load_access()
    if email in data.get("pending", {}):
        data["pending"].pop(email, None)
        _save_access(data)


# --------------------------------------------------------------------------- #
# Admin approvals panel (rendered in the main area — the dashboard is sidebar-less)
# --------------------------------------------------------------------------- #
def admin_panel():
    """Admin-only approvals UI, rendered in the main content area. No-op unless
    auth is enabled and the signed-in user is an admin."""
    if not auth_enabled():
        return
    email, _ = _current()
    if not email or not is_admin(email):
        return
    data = _load_access()
    with st.expander(f"Admin — approvals ({len(data['pending'])} pending)"):
        for pemail, pname in list(data["pending"].items()):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{pemail}" + (f" · {pname}" if pname else ""))
            if c2.button("Approve", key=f"approve_{pemail}"):
                data["approved"] = sorted(set(data["approved"]) | {pemail})
                data["pending"].pop(pemail, None)
                _save_access(data)
                ok, info = notifications.send_approval_email(pemail, pname)
                if ok:
                    st.toast(f"Approved {pemail} — email sent")
                elif info == "email not configured":
                    st.toast(f"Approved {pemail}")
                else:
                    st.toast(f"Approved {pemail}; email failed: {info}")
                st.rerun()
        if not data["pending"]:
            st.caption("No pending requests.")
        new = st.text_input("Add an email to the allow-list", key="admin_add_email")
        if st.button("Add", key="admin_add_btn") and new.strip():
            data["approved"] = sorted(set(data["approved"]) | {new.strip().lower()})
            data["pending"].pop(new.strip().lower(), None)
            _save_access(data)
            st.rerun()
        if data["approved"]:
            st.caption("Approved: " + ", ".join(data["approved"]))


def is_admin(email) -> bool:
    email = (email or "").strip().lower()
    if not email:
        return False
    return email in set(a.lower() for a in _load_access()["admins"])


def header_account():
    """Signed-in avatar + name chip, rendered in the main area (top bar). No-op
    unless auth is enabled and a user is signed in."""
    if not auth_enabled():
        return
    email, name = _current()
    if not email:
        return
    who = name or email
    initial = (who[:1] or "?").upper()
    cc1, cc2 = st.columns([2, 1], vertical_alignment="center")
    cc1.markdown(
        f"<div style='display:flex;align-items:center;justify-content:flex-end;"
        f"height:38px;gap:6px'>"
        f"<span class='avatar' style='display:inline-flex'>{html.escape(initial)}</span>"
        f"<span style='color:var(--muted)'>{html.escape(who)}</span></div>",
        unsafe_allow_html=True,
    )
    cc2.button("logout", on_click=_logout, key="hdr_logout")
