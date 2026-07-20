# Streamlit Demo Deployment — Design (Phase 1)

**Date:** 2026-07-20
**Repo:** `bapipe-keypoints/` (existing git repo, branch `feature/dashboard-bw-redesign`)
**App:** `gui_app/` — Streamlit dashboard over the bapipe-keypoints behavioural analysis pipeline.

## Goal

Ship a **Docker-deployable demo** of the existing `gui_app` Streamlit dashboard:
users log in (email/password + admin approval), explore analysis dashboards on a
**bundled sample dataset**, and save/re-view their own analysis results. Deployable
anywhere via container. This is Phase 1 of a two-phase plan.

**Phase 2 (later, out of scope here):** researchers upload their own data
(`datafiles.csv` + videos + `.h5`), processed **ephemerally** and discarded — no
persistent storage of uploaded raw data.

## Confirmed decisions

- **Deploy target:** Docker container ("deploy anywhere"). bapipe already has
  `docker/` build files to draw from.
- **Auth:** Keep the existing **email/password + admin-approval allow-list**.
  **Drop Google (OIDC)** for Phase 1 → the exposed `client_secret*.json` is unused
  and must never be committed (re-issue it in Phase 2 if Google is revived).
- **Results storage:** **Keep** `records.py` — per-user analysis result snapshots
  (numbers + metadata only; never raw video/pose). Purpose: a logged-in user can
  re-view *their own* results. Privacy stance "we don't collect": results are
  private to the owning user (already enforced by per-user file isolation); the
  operator does not aggregate, read, or export them.
- **No raw-data collection:** the app never persists uploaded raw video/pose data.
- **Domain/hosting:** Phase 1 targets **Hugging Face Spaces (Docker SDK)** — the
  easiest free option (16 GB RAM free, Docker-native). The image stays
  **platform-neutral** so Fly.io / Cloud Run / self-host work later with a thin
  adapter. Public URL is config-driven; nothing hardcoded to a domain.
- **Persistence:** deferred. HF Spaces free storage is **ephemeral** (resets on
  restart/rebuild) — accepted for the demo. Admin accounts are the durable source
  of truth, re-seeded from `BAPIPE_ADMINS` env on every start; self-registered
  users and saved results may reset on restart, which is fine for Phase 1. A
  durable-volume host (Fly.io) is a later, non-blocking upgrade.

## Scope

**In scope (Phase 1):**
- Dockerization of `gui_app` for anywhere-deployment.
- Auth productionization: remove Google path, keep email/password + approval,
  move secrets to env, persist auth + records state across container restarts.
- Bundled lightweight **sample dataset** for the demo (NOT the 7 GB datasets).

**Out of scope (Phase 2+):** user upload flow, ephemeral processing, object
storage, Google login, CI/CD pipeline (may be added later), custom domain/HTTPS
termination (host-specific; app only needs to be reverse-proxy friendly),
**durable persistence** (HF Spaces ephemeral storage accepted for now; Fly.io or
a mounted volume is a later upgrade).

## Groundwork (sequential, done before agents)

- **Git:** repo already exists at `bapipe-keypoints/`; the 7 GB datasets and
  `client_secret*.json` live *outside* this repo, so they cannot be committed here.
- **`.gitignore` hardened** (this commit): ignore `**/.streamlit/secrets.toml` and
  `client_secret*.json` as defense-in-depth. `users.json`, `access.json`,
  `records/` were already ignored.

## Shared contract (locked before parallel work)

The two agents touch disjoint files except for one shared interface — the
**persistent state layout** and **env schema**. Both must agree on:

- **State dir:** `/data` inside the container, holding:
  - `/data/records/` — per-user result snapshots
  - `/data/users.json` — registered users (bcrypt-hashed)
  - `/data/access.json` — admin approval list

  On HF Spaces this dir is **ephemeral** (Phase 1 accepts resets). The code path
  is identical whether `/data` is a real volume (local/Fly.io) or ephemeral (HF),
  so no app change is needed to add durability later — only the host config.
- **Env vars:**
  - `BAPIPE_RECORDS_DIR=/data/records`
  - `BAPIPE_USERS_FILE=/data/users.json` (auth agent introduces this if not present)
  - `BAPIPE_ACCESS_FILE=/data/access.json`
  - `BAPIPE_ADMINS` — comma-separated admin emails (replaces committed secret)
  - Streamlit server config via `.streamlit/config.toml` + env as needed.
- **Secrets:** provided at runtime via env / mounted `secrets.toml`; never baked
  into the image, never committed.

`records.py` already honors `BAPIPE_RECORDS_DIR`. The auth agent generalizes the
same pattern to `users.json` / `access.json` (currently hardcoded next to the
module) so they land on the volume.

## Components / agents (parallel)

### Agent A — Docker deployment infrastructure
**Owns (all new files):** `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
`entrypoint.sh`, `gui_app/.streamlit/config.toml`, plus HF Spaces glue
(`README.md` Space header / `app_port` config, listen on `0.0.0.0` and the
platform port — 7860 on HF, `$PORT` elsewhere).

- Base: Python **3.11** (bapipe pins pandas 1.5.x / numpy 1.x — see
  `gui_app/requirements.txt`).
- System deps: `ffmpeg`, HDF5 libs (for `tables`), OpenCV runtime libs.
- Install `gui_app/requirements.txt` + the local `bapipe` source (`../src`).
- Persistent volume mount at `/data`; wire the contract env vars.
- Streamlit config for running behind a reverse proxy (address/port, CORS/XSRF,
  `baseUrlPath` if needed) — proxy-friendly, host-agnostic.
- Bundle or mount a **trimmed sample dataset** so the demo has something to show;
  keep it small (megabytes, not the 7 GB archives) and exclude big archives via
  `.dockerignore`.
- Deliver a working `docker compose up` that serves the dashboard, plus a smoke
  check that the container starts and the login page renders.

### Agent C — Auth productionization
**Owns:** `gui_app/auth.py`, `gui_app/records.py` (paths only), secrets/env schema;
keep `gui_app/tests/test_auth.py` green.

- Remove / disable the Google (OIDC) code path and its `st.login` usage; keep the
  file working with **no Google secrets present**.
- Keep email/password self-registration + bcrypt + admin-approval allow-list.
- Move admin list and any secrets from committed files to **env** (`BAPIPE_ADMINS`
  etc.); make `users.json` / `access.json` paths point at the `/data` volume via
  env (matching the shared contract).
- Review multi-user web session behavior (email/password state currently lost on
  full refresh) and document/adjust as needed for a deployed demo.
- Update/extend `test_auth.py` to cover the Google-removed, env-configured paths.

**Isolation:** A and C edit disjoint files (A = new infra files; C = `auth.py` +
`records.py` path lines), so they run in parallel without worktrees. The only
coupling is the shared contract above, locked before dispatch.

## Testing

- Existing suite: `gui_app/tests/` (`test_app_smoke`, `test_auth`, `test_records`,
  `test_routing`, `test_theme`) must stay green.
- Agent C extends `test_auth.py` for the new env-driven, Google-removed auth.
- Agent A adds a container smoke check (starts, health OK, login page renders).
- Full CI/CD pipeline deferred to a later phase.

## Risks / notes

- **pandas/numpy pinning:** the image must use Python 3.11 and the pinned deps or
  bapipe breaks at import. Non-negotiable.
- **State persistence:** on HF Spaces `/data` is ephemeral, so self-registered
  users and saved results reset on restart — accepted for Phase 1. Admins are
  re-seeded from `BAPIPE_ADMINS` so the app is always usable after a restart.
  Durable storage (Fly.io volume / mounted disk) is a later, non-blocking upgrade
  requiring only host config, no code change.
- **Exposed client secret:** `client_secret*.json` in Downloads is now
  gitignored and unused in Phase 1; recommend re-issuing before any Phase 2 Google
  revival.
