#!/usr/bin/env bash
# One command for the whole app: the agent server (port 8000) and the UI (port 5173).
#   ./scripts/dev.sh
# The UI goes live by itself when the server is up and .env has SENSO_API_KEY and SIE_API_KEY;
# otherwise it replays the recorded runs in contracts/. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r server/requirements.txt -r agent/requirements.txt

.venv/bin/uvicorn server.app:app --port 8000 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT

cd web
[ -d node_modules ] || npm install
npm run dev
