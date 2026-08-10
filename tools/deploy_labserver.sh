#!/usr/bin/env bash
# Deploy the dashboard on a self-hosted Ubuntu server with Docker.
#
# Data, uploads and temp files are kept on a big-disk path (default /backup/bapipe)
# because the OS root disk is often small/full. Uploads are multi-GB, so /tmp must
# NOT sit on a nearly-full root — this mounts a big-disk dir as the container /tmp.
#
# Run from the repo root on the server:
#   BAPIPE_ADMINS="you@lab.ca" BAPIPE_ADMIN_PASSWORD="secret" ./tools/deploy_labserver.sh
#
# Env:
#   BAPIPE_ADMINS          (required) comma-separated admin emails
#   BAPIPE_ADMIN_PASSWORD  (optional) seeds admin login so it survives restarts
#   BAPIPE_DATA_ROOT       (optional) big-disk base dir   [default /backup/bapipe]
#   PORT                   (optional) host port           [default 7860]
set -euo pipefail

DATA_ROOT="${BAPIPE_DATA_ROOT:-/backup/bapipe}"
ADMINS="${BAPIPE_ADMINS:?set BAPIPE_ADMINS=you@lab.ca}"
PORT="${PORT:-7860}"
IMAGE="bapipe-dashboard"

command -v docker >/dev/null || {
  echo "Docker not found. Install it first:"
  echo "  curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker \$USER"
  echo "  (log out/in, then re-run this script)"; exit 1; }

echo "Data root : $DATA_ROOT   (data + uploads/temp live here, off the root disk)"
mkdir -p "$DATA_ROOT/data" "$DATA_ROOT/tmp"

echo "Building image…"
docker build -t "$IMAGE" .

echo "Starting container…"
docker rm -f bapipe 2>/dev/null || true
docker run -d --name bapipe --restart unless-stopped \
  -p "${PORT}:7860" \
  -v "$DATA_ROOT/data:/data" \
  -v "$DATA_ROOT/tmp:/tmp" \
  -e BAPIPE_ADMINS="$ADMINS" \
  -e BAPIPE_ALLOW_SERVER_PATHS=1 \
  ${BAPIPE_ADMIN_PASSWORD:+-e BAPIPE_ADMIN_PASSWORD="$BAPIPE_ADMIN_PASSWORD"} \
  "$IMAGE"

ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "✓ Up. Open:  http://${ip:-<server-ip>}:${PORT}"
echo "  Logs:      docker logs -f bapipe"
echo "  Update:    git pull && ./tools/deploy_labserver.sh   (rebuild + restart)"
echo "  If firewalled:  sudo ufw allow ${PORT}/tcp"
