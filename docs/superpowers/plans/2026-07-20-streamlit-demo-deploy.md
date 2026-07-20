# Streamlit Demo Deployment (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Docker-deployable, login-gated demo of the `gui_app` Streamlit dashboard, runnable free on Hugging Face Spaces (Docker SDK).

**Architecture:** Two independent tracks against a locked env contract. **Track C** productionizes auth (env-driven admin seeding + state paths, Google/OIDC removed). **Track A** adds a platform-neutral Docker image + HF Spaces glue. Tracks touch disjoint files and run in parallel.

**Tech Stack:** Python 3.11, Streamlit, bcrypt, Docker, Hugging Face Spaces (Docker SDK). Scientific stack pinned in `gui_app/requirements.txt` (numpy 1.26.4 / pandas 1.5.3).

## Global Constraints

- **Python 3.11 only** — bapipe targets pandas 1.5.x / numpy 1.x; newer breaks import.
- **No Google/OIDC** in Phase 1 — no `st.login`/`st.logout`/`st.user`, no authlib requirement at runtime.
- **No committed secrets** — admins & any secret come from env / mounted `secrets.toml`; never baked into the image or committed.
- **Env contract (both tracks must use these exact names):**
  - `BAPIPE_RECORDS_DIR` → default `/data/records` (already honored by `records.py`)
  - `BAPIPE_USERS_FILE` → default `/data/users.json`
  - `BAPIPE_ACCESS_FILE` → default `/data/access.json`
  - `BAPIPE_ADMINS` → comma-separated admin emails
- **HF Spaces:** app listens on `0.0.0.0:$PORT` (default `7860`); Space `app_port: 7860`.
- **State dir `/data` is ephemeral on HF** (accepted); admins re-seed from `BAPIPE_ADMINS` on every start.
- Repo root for all paths below: `bapipe-keypoints/`. Run tests with the project's Python 3.11 (`~/.local/bin/python3.11` or `.venv`).

## File Structure

**Track C (auth) — modifies:**
- `gui_app/auth.py` — env-driven state-file paths + admin seeding; Google path removed.
- `gui_app/tests/test_auth.py` — extended coverage.
- `gui_app/records.py` — **no change** (already reads `BAPIPE_RECORDS_DIR`); listed only to confirm the contract.

**Track A (docker/HF) — creates (all new):**
- `Dockerfile`
- `.dockerignore`
- `entrypoint.sh`
- `docker-compose.yml`
- `gui_app/.streamlit/config.toml`
- `deploy/hf-space-README.md` (becomes the HF Space repo's `README.md`)
- `docs/DEPLOY.md` (deploy runbook)

Disjoint file sets → no merge conflicts. The only shared surface is the env-var contract above, already locked.

---

## Track C — Auth productionization

### Task C1: Env-overridable state-file paths

**Files:**
- Modify: `gui_app/auth.py` (constants at lines 24-26; funcs `_load_access`/`_save_access`/`_load_users`/`_save_users` at 65-92)
- Test: `gui_app/tests/test_auth.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `auth._access_file() -> Path`, `auth._users_file() -> Path` reading `BAPIPE_ACCESS_FILE` / `BAPIPE_USERS_FILE` (fallback to `HERE/…`). Save functions create parent dirs.

- [ ] **Step 1: Write the failing test**

Add to `gui_app/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py::test_state_files_follow_env -v`
Expected: FAIL with `AttributeError: module 'auth' has no attribute '_users_file'`

- [ ] **Step 3: Implement**

In `gui_app/auth.py`, add `import os` (with the other stdlib imports) and replace the constants block:

```python
HERE = Path(__file__).resolve().parent
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _access_file() -> Path:
    return Path(os.environ.get("BAPIPE_ACCESS_FILE", str(HERE / "access.json")))


def _users_file() -> Path:
    return Path(os.environ.get("BAPIPE_USERS_FILE", str(HERE / "users.json")))
```

Then update the four storage functions to use them (and create parent dirs on save):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py -v`
Expected: PASS (new test + existing `test_is_admin_reads_access`)

- [ ] **Step 5: Commit**

```bash
git add gui_app/auth.py gui_app/tests/test_auth.py
git commit -m "feat(auth): env-overridable users/access state paths"
```

### Task C2: Seed admins from BAPIPE_ADMINS env + env-driven enablement

**Files:**
- Modify: `gui_app/auth.py` (`_seed_admins` at 57-62, `auth_enabled` at 40-41)
- Test: `gui_app/tests/test_auth.py`

**Interfaces:**
- Consumes: `_access_file`/`_users_file` from C1.
- Produces: `_seed_admins()` merges secrets `[access].admins` with `BAPIPE_ADMINS`; `auth_enabled()` returns True when any admin is configured.

- [ ] **Step 1: Write the failing test**

```python
def test_admins_and_enablement_from_env(monkeypatch):
    monkeypatch.setenv("BAPIPE_ADMINS", "Boss@x.com, two@x.com ")
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: None)  # no secrets.toml
    assert auth._seed_admins() == ["boss@x.com", "two@x.com"]
    assert auth.auth_enabled() is True
    assert auth.is_admin("BOSS@x.com") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py::test_admins_and_enablement_from_env -v`
Expected: FAIL (`auth_enabled()` is False — env not consulted yet)

- [ ] **Step 3: Implement**

Replace `_seed_admins` and `auth_enabled` in `gui_app/auth.py`:

```python
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


def auth_enabled():
    return bool(_seed_admins()) or _secret("access") is not None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui_app/auth.py gui_app/tests/test_auth.py
git commit -m "feat(auth): seed admins + enable auth from BAPIPE_ADMINS env"
```

### Task C3: Remove Google (OIDC) path

**Files:**
- Modify: `gui_app/auth.py` (`google_enabled` 44-51, `_current` 144-151, `_logout` 159-163, `_login_page` Google button 223-226, module docstring 1-15)
- Test: `gui_app/tests/test_auth.py`

**Interfaces:**
- Consumes: C1/C2.
- Produces: `google_enabled()` always False; `_current()`/`_logout()` never touch `st.user`/`st.login`/`st.logout`.

- [ ] **Step 1: Write the failing test**

```python
def test_google_disabled_even_with_auth_secret(monkeypatch):
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_secret", lambda section: {"x": 1} if section == "auth" else None)
    assert auth.google_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py::test_google_disabled_even_with_auth_secret -v`
Expected: FAIL (current `google_enabled()` returns True when `[auth]` + authlib present)

- [ ] **Step 3: Implement**

In `gui_app/auth.py`:

Replace `google_enabled`:

```python
def google_enabled():
    # Google/OIDC removed for the Phase 1 demo. Always disabled.
    return False
```

Simplify `_current` (drop the `st.user` branch):

```python
def _current():
    """Return (email, name) of the signed-in user, or (None, None)."""
    email = st.session_state.get("auth_email")
    if email:
        return email, st.session_state.get("auth_name", "")
    return None, None
```

Simplify `_logout` (drop `st.logout`):

```python
def _logout():
    st.session_state.pop("auth_email", None)
    st.session_state.pop("auth_name", None)
```

In `_login_page`, delete the Google block (lines 223-226):

```python
        if google_enabled():
            st.markdown("<div style='text-align:center;color:#888;margin:0.3rem 0'>or</div>",
                        unsafe_allow_html=True)
            st.button("Log in with Google", on_click=st.login, use_container_width=True)
```

Update the module docstring (lines 1-15) to describe email/password + admin-approval only, admins from `BAPIPE_ADMINS` env or `secrets["access"]["admins"]`; remove Google references.

- [ ] **Step 4: Run tests to verify pass**

Run: `cd gui_app && python3.11 -m pytest tests/test_auth.py -v`
Expected: PASS (all C tests + original)

- [ ] **Step 5: Commit**

```bash
git add gui_app/auth.py gui_app/tests/test_auth.py
git commit -m "refactor(auth): remove Google/OIDC path (phase-1 demo)"
```

---

## Track A — Docker image + HF Spaces glue

### Task A1: Streamlit server config

**Files:**
- Create: `gui_app/.streamlit/config.toml`

- [ ] **Step 1: Write the config**

```toml
# Proxy-friendly defaults for containerized / HF Spaces deployment.
[server]
headless = true
address = "0.0.0.0"
port = 7860
enableCORS = false
enableXsrfProtection = false
maxUploadSize = 2048

[browser]
gatherUsageStats = false

[theme]
base = "light"
```

- [ ] **Step 2: Verify it parses**

Run: `python3.11 -c "import tomllib,sys; tomllib.load(open('gui_app/.streamlit/config.toml','rb')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add gui_app/.streamlit/config.toml
git commit -m "chore(deploy): streamlit server config for containers"
```

### Task A2: Dockerfile + .dockerignore + entrypoint

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `entrypoint.sh`

**Interfaces:**
- Consumes: env contract (Global Constraints); `gui_app/app.py` adds `../src` to `sys.path`, so `bapipe` is imported from source — no pip install of bapipe needed, just copy `src/`.

- [ ] **Step 1: Write `.dockerignore`**

```
.git/
**/__pycache__/
**/*.pyc
.venv/
gui_app/.venv/
gui_app/users.json
gui_app/access.json
gui_app/records/
**/.streamlit/secrets.toml
client_secret*.json
docs/
docs.bk/
_build/
*.zip
.DS_Store
**/.DS_Store
```

- [ ] **Step 2: Write `entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -e
mkdir -p "${BAPIPE_RECORDS_DIR:-/data/records}"
mkdir -p "$(dirname "${BAPIPE_USERS_FILE:-/data/users.json}")"
exec streamlit run /app/gui_app/app.py \
    --server.port "${PORT:-7860}" \
    --server.address 0.0.0.0
```

- [ ] **Step 3: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

# System libraries: ffmpeg (imageio video export), libGL/glib (opencv),
# HDF5 (pytables), all required by gui_app/requirements.txt at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first for layer caching.
COPY gui_app/requirements.txt /app/gui_app/requirements.txt
RUN pip install --no-cache-dir -r /app/gui_app/requirements.txt

# App + bapipe library source (imported via sys.path in app.py).
COPY src /app/src
COPY gui_app /app/gui_app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Ephemeral state dir (HF Spaces resets it; mount a volume elsewhere for durability).
ENV BAPIPE_RECORDS_DIR=/data/records \
    BAPIPE_USERS_FILE=/data/users.json \
    BAPIPE_ACCESS_FILE=/data/access.json \
    PORT=7860
RUN mkdir -p /data/records && chmod -R 777 /data

EXPOSE 7860
ENTRYPOINT ["/app/entrypoint.sh"]
```

- [ ] **Step 4: Build the image**

Run: `docker build -t bapipe-demo .`
Expected: build completes; final line `naming to docker.io/library/bapipe-demo`.

- [ ] **Step 5: Smoke-test the running container**

Run:
```bash
docker run -d --name bapipe-smoke -e BAPIPE_ADMINS=admin@example.com -p 7860:7860 bapipe-demo
sleep 15
curl -sf http://localhost:7860/_stcore/health && echo " HEALTH_OK"
docker rm -f bapipe-smoke
```
Expected: `ok HEALTH_OK` (Streamlit health endpoint returns `ok`).

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore entrypoint.sh
git commit -m "feat(deploy): docker image for the streamlit demo"
```

### Task A3: docker-compose for local runs

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  dashboard:
    build: .
    ports:
      - "7860:7860"
    environment:
      BAPIPE_ADMINS: "admin@example.com"
    volumes:
      - bapipe_data:/data          # durable users/records for LOCAL runs
      # - ./sample_data:/data/sample:ro  # optional: demo dataset folder to enter in the wizard

volumes:
  bapipe_data:
```

- [ ] **Step 2: Verify compose config**

Run: `docker compose config -q && echo COMPOSE_OK`
Expected: `COMPOSE_OK`

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(deploy): docker-compose for local runs"
```

### Task A4: HF Spaces README + deploy runbook

**Files:**
- Create: `deploy/hf-space-README.md`, `docs/DEPLOY.md`

- [ ] **Step 1: Write `deploy/hf-space-README.md`** (becomes the Space repo's `README.md`)

```markdown
---
title: Animal Behaviour Analysis
emoji: 🐭
colorFrom: gray
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Animal Behaviour Analysis — Demo

Login-gated Streamlit dashboard (bapipe-keypoints). See `docs/DEPLOY.md` in the
source repo for setup. Admins are configured via the `BAPIPE_ADMINS` Space secret.
```

- [ ] **Step 2: Write `docs/DEPLOY.md`** (runbook)

```markdown
# Deploying the demo to Hugging Face Spaces (Docker)

## One-time setup
1. Create a new Space: **SDK = Docker**, hardware = free CPU basic.
2. In the Space repo, use `deploy/hf-space-README.md` as `README.md`
   (the YAML header sets `sdk: docker` and `app_port: 7860`).
3. Space **Settings → Variables and secrets**: add secret
   `BAPIPE_ADMINS = you@example.com` (comma-separated for multiple admins).

## Push the code
Add the Space as a git remote and push the repo root (which holds `Dockerfile`):
```bash
git remote add space https://huggingface.co/spaces/<user>/<space>
git push space HEAD:main
```
The Space builds the Dockerfile and serves on port 7860.

## Notes
- Storage is **ephemeral** on the free tier: self-registered users and saved
  results reset on restart. Admins always come back from `BAPIPE_ADMINS`.
- For durable state, deploy the same image to Fly.io with a volume mounted at
  `/data` — no code change required.
- Local run: `docker compose up` → http://localhost:7860.
```

- [ ] **Step 3: Verify markdown front-matter**

Run: `python3.11 -c "import re; t=open('deploy/hf-space-README.md').read(); assert t.startswith('---') and 'app_port: 7860' in t; print('FM_OK')"`
Expected: `FM_OK`

- [ ] **Step 4: Commit**

```bash
git add deploy/hf-space-README.md docs/DEPLOY.md
git commit -m "docs(deploy): HF Space README + deploy runbook"
```

---

## Parallel execution

Track C (C1→C2→C3) and Track A (A1→A2→A3→A4) share no files and can run as two
parallel agents. Within a track, tasks are sequential. After both tracks finish,
run the full suite once and a container smoke test:

```bash
cd gui_app && python3.11 -m pytest tests/ -v      # all green
docker build -t bapipe-demo .. && docker run -d --name v -e BAPIPE_ADMINS=a@b.com -p 7860:7860 bapipe-demo && sleep 15 && curl -sf localhost:7860/_stcore/health && docker rm -f v
```

## Self-Review

- **Spec coverage:** Docker image (A2) ✓, HF Spaces target + app_port 7860 (A1/A4) ✓, platform-neutral image (A2/A3) ✓, email/password + approval kept (untouched core of auth.py) ✓, Google removed (C3) ✓, admins from env / no committed secrets (C2) ✓, `/data` state + env contract (A2/C1) ✓, records kept & already env-driven (noted, no change) ✓, ephemeral-accepted + admin re-seed (A4/C2) ✓.
- **Deferred (spec §out-of-scope):** upload flow, durable persistence, curated bundled sample dataset (operator supplies a folder via the optional `./sample_data` mount in A3), CI/CD.
- **Placeholders:** none — every code/config step is complete.
- **Type consistency:** `_access_file`/`_users_file` (C1) used by C2/C3; `BAPIPE_ADMINS`/`BAPIPE_USERS_FILE`/`BAPIPE_ACCESS_FILE`/`BAPIPE_RECORDS_DIR` identical across Dockerfile (A2), entrypoint (A2), compose (A3), and auth.py (C1/C2).
