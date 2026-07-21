#!/usr/bin/env bash
set -e
mkdir -p "${BAPIPE_RECORDS_DIR:-/data/records}"
mkdir -p "$(dirname "${BAPIPE_USERS_FILE:-/data/users.json}")"
mkdir -p "$(dirname "${BAPIPE_ACCESS_FILE:-/data/access.json}")"
# Launch from the app dir so Streamlit loads gui_app/.streamlit/config.toml.
# Server host/port/proxy flags live HERE (not in config.toml) so the committed
# config stays safe for Streamlit Community Cloud, which manages host/port itself.
cd /app/gui_app
exec streamlit run app.py \
    --server.port "${PORT:-7860}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
