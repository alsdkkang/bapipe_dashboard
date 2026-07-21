#!/usr/bin/env bash
set -e
mkdir -p "${BAPIPE_RECORDS_DIR:-/data/records}"
mkdir -p "$(dirname "${BAPIPE_USERS_FILE:-/data/users.json}")"
exec streamlit run /app/gui_app/app.py \
    --server.port "${PORT:-7860}" \
    --server.address 0.0.0.0
