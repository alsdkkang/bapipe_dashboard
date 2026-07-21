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
