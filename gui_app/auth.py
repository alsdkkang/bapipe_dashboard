"""Login for the bapipe dashboard: email/password (bcrypt) + optional Google (OIDC),
gated by an admin-approved allow-list.

Auth is ENABLED only when `.streamlit/secrets.toml` has an `[access]` section (admins)
and/or an `[auth]` section (Google). With no secrets everything here is a no-op, so the
app keeps running locally without any credentials.

- **Email/password**: users self-register; new accounts are stored in `gui_app/users.json`
  (bcrypt-hashed) and land in the pending list until an admin approves them. Login state is
  kept in `st.session_state` (a full browser refresh logs the email/password user out —
  Google login persists via Streamlit's own cookie).
- **Google**: available when `[auth]` is configured; uses Streamlit's native `st.login`.
- **Admins** (from `secrets["access"]["admins"]`) are always allowed and approve others from
  the sidebar. Approvals live in `gui_app/access.json`.
"""
import json
import re
from pathlib import Path

import bcrypt
import streamlit as st

HERE = Path(__file__).resolve().parent
ACCESS_FILE = HERE / "access.json"
USERS_FILE = HERE / "users.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- #
# Config / enablement
# --------------------------------------------------------------------------- #
def _secret(section):
    try:
        return st.secrets[section]
    except Exception:
        return None


def auth_enabled():
    return _secret("access") is not None or _secret("auth") is not None


def google_enabled():
    if _secret("auth") is None:
        return False
    try:
        import authlib  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _seed_admins():
    acc = _secret("access")
    try:
        return [e.strip().lower() for e in acc["admins"]]
    except Exception:
        return []


def _load_access():
    data = {"admins": [], "approved": [], "pending": {}}
    if ACCESS_FILE.exists():
        try:
            data.update(json.loads(ACCESS_FILE.read_text()))
        except Exception:
            pass
    data["admins"] = sorted(set(data.get("admins", [])) | set(_seed_admins()))
    data.setdefault("approved", [])
    data.setdefault("pending", {})
    return data


def _save_access(data):
    ACCESS_FILE.write_text(json.dumps(data, indent=2))


def _load_users():
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2))


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
    if google_enabled() and getattr(st.user, "is_logged_in", False):
        return (st.user.email or "").lower(), getattr(st.user, "name", "") or ""
    email = st.session_state.get("auth_email")
    if email:
        return email, st.session_state.get("auth_name", "")
    return None, None


def current_user():
    """Public: (email, name) of the signed-in user, or (None, None)."""
    return _current()


def _logout():
    if google_enabled() and getattr(st.user, "is_logged_in", False):
        st.logout()
    st.session_state.pop("auth_email", None)
    st.session_state.pop("auth_name", None)


# --------------------------------------------------------------------------- #
# Login page
# --------------------------------------------------------------------------- #
def _render_logo(logo_path):
    if logo_path and Path(logo_path).exists():
        if str(logo_path).endswith(".svg"):
            st.image(Path(logo_path).read_text(), width=110)
        else:
            st.image(str(logo_path), width=110)


def _login_page(logo_path):
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        _render_logo(logo_path)
        st.title("bapipe dashboard")
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

        if google_enabled():
            st.markdown("<div style='text-align:center;color:#888;margin:0.3rem 0'>or</div>",
                        unsafe_allow_html=True)
            st.button("Log in with Google", on_click=st.login, use_container_width=True)

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
# Sidebar account + admin panel
# --------------------------------------------------------------------------- #
def sidebar_account():
    if not auth_enabled():
        return
    email, _ = _current()
    if not email:
        return
    data = _load_access()
    is_admin = email in set(data["admins"])

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Signed in as {email}{' (admin)' if is_admin else ''}")
    st.sidebar.button("Log out", on_click=_logout, use_container_width=True)

    if not is_admin:
        return
    with st.sidebar.expander(f"Admin — approvals ({len(data['pending'])} pending)"):
        for pemail, pname in list(data["pending"].items()):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{pemail}" + (f" · {pname}" if pname else ""))
            if c2.button("Approve", key=f"approve_{pemail}"):
                data["approved"] = sorted(set(data["approved"]) | {pemail})
                data["pending"].pop(pemail, None)
                _save_access(data)
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
    """Signed-in avatar + logout, rendered in the main area (top bar). No-op
    unless auth is enabled and a user is signed in."""
    if not auth_enabled():
        return
    email, name = _current()
    if not email:
        return
    who = name or email
    initial = (who[:1] or "?").upper()
    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    c1.markdown(
        f"<div style='text-align:right'>"
        f"<span class='avatar' style='display:inline-flex;vertical-align:middle;margin-right:6px'>{initial}</span>"
        f"<span style='color:#6c7889'>{who}</span></div>",
        unsafe_allow_html=True,
    )
    c2.button("Log out", on_click=_logout, use_container_width=True, key="hdr_logout")
