# Deploying the demo

## Phase 1 (now): Streamlit Community Cloud — free

The easiest free host for this Streamlit app. No Docker needed; it installs from
`requirements.txt` (Python deps) + `packages.txt` (apt deps) at the repo root.

### Prerequisites
- The code must live in **your own GitHub repo** (the current `origin` is the
  upstream author's repo). Create a repo under your account and push this branch.

### Steps
1. Push this repo to your GitHub (one-time):
   ```bash
   git remote add myrepo https://github.com/<you>/<repo>.git
   git push -u myrepo HEAD:main
   ```
2. Go to https://share.streamlit.io → **Create app** → pick your repo/branch.
3. Set **Main file path** to `gui_app/app.py`.
4. **Advanced settings → Python version = 3.11** (required — bapipe needs pandas
   1.5.x / numpy 1.x).
5. **Advanced settings → Secrets**: paste (TOML) to enable login + admin approval:
   ```toml
   [access]
   admins = ["you@example.com"]

   # Optional: email approved users "you can now log in" (Gmail SMTP).
   # Needs 2-Step Verification on the Gmail account + an App Password
   # (https://myaccount.google.com/apppasswords). Omit this section to skip email.
   [email]
   sender = "you@gmail.com"
   app_password = "abcd efgh ijkl mnop"
   app_url = "https://your-app.streamlit.app"
   ```
   Without the `[access]` secret, auth is disabled and the app is open to everyone.
   Without `[email]`, approvals still work but no email is sent.
6. **Deploy**. First build takes a few minutes (installs ffmpeg / HDF5 / the
   scientific stack). You get a `https://<app>.streamlit.app` URL.

### Notes
- Storage is **ephemeral**: self-registered users and saved results reset on
  reboot/redeploy. Admins always come back from the `[access]` secret.
- RAM is ~1 GB — fine for the login demo. Heavy per-experiment video processing
  (Phase 2) may hit the ceiling → that's the trigger to move to Cloud Run.

## Later (scaling): Google Cloud Run — free tier, Docker

When Phase 2 (researcher uploads + video processing) or real traffic arrives,
move to Cloud Run using the `Dockerfile` already in this repo. Cloud Run lets you
raise memory/CPU, add a custom domain, and attach Cloud Storage for uploads — no
app code change. Set the admin list via the `BAPIPE_ADMINS` env var (comma-
separated) instead of the `[access]` secret.

- Durable state alternative: Fly.io with a volume mounted at `/data`.
- Local run of the container: `docker compose up` → http://localhost:7860.
