#!/usr/bin/env bash
set -e
mkdir -p "${BAPIPE_RECORDS_DIR:-/data/records}"
mkdir -p "$(dirname "${BAPIPE_USERS_FILE:-/data/users.json}")"
mkdir -p "$(dirname "${BAPIPE_ACCESS_FILE:-/data/access.json}")"
# Launch from the app dir so Streamlit loads gui_app/.streamlit/config.toml —
# Streamlit reads the project config from the launch CWD, not the script's dir.
# (--server.* CLI flags below still override the file for port/address.)
cd /app/gui_app
exec streamlit run app.py \
    --server.port "${PORT:-7860}" \
    --server.address 0.0.0.0
