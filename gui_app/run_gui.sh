#!/usr/bin/env bash
# Launch the bapipe analysis dashboard.
# Uses the project's .venv if present, otherwise whatever streamlit is on PATH.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DIR/.." && pwd)"

if [ -x "$REPO/.venv/bin/streamlit" ]; then
  exec "$REPO/.venv/bin/streamlit" run "$DIR/app.py" "$@"
else
  exec streamlit run "$DIR/app.py" "$@"
fi
