# Deploying the demo to Hugging Face Spaces (Docker)

The repo root `README.md` already carries the HF front-matter
(`sdk: docker`, `app_port: 7860`), so pushing this repo to a Space builds and
serves the Dockerfile directly — no file copying needed.

## One-time setup
1. Create a new Space on Hugging Face: **SDK = Docker**, hardware = free CPU basic.
2. Space **Settings → Variables and secrets** → add a secret
   `BAPIPE_ADMINS = you@example.com` (comma-separated for multiple admins).
   Without it, auth is disabled and the app is open to everyone.

## Push the code
Add the Space as a git remote and push (⚠️ use a NEW remote named `space` — do
NOT push to `origin`, which is the upstream author's repo):
```bash
git remote add space https://huggingface.co/spaces/<user>/<space>
git push space HEAD:main
```
HF builds the root `Dockerfile` and serves Streamlit on port 7860. The first
build takes a few minutes (installs ffmpeg / HDF5 / the scientific stack).

## Verify
- Open the Space URL → you should land on the login page (auth is on because
  `BAPIPE_ADMINS` is set).
- Self-register, then approve the account from the sidebar Admin panel while
  logged in as an admin email listed in `BAPIPE_ADMINS`.

## Notes
- Storage is **ephemeral** on the free tier: self-registered users and saved
  results reset on restart. Admins always come back from `BAPIPE_ADMINS`.
- For durable state, deploy the same image to Fly.io with a volume mounted at
  `/data` — no code change required.
- Local run: `docker compose up` → http://localhost:7860.
