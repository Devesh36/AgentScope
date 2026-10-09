#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root_dir="$PWD"
mkdir -p .local
if [[ ! -x .venv/bin/uvicorn || ! -d apps/web/node_modules ]]; then
  printf 'Dependencies missing. Run npm run setup first.\n' >&2
  exit 1
fi
(cd apps/api && ../../.venv/bin/alembic upgrade head)
(cd apps/api && exec ../../.venv/bin/uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port "${API_PORT:-8000}") &
api_pid=$!
web_pid=''
cleanup() { kill "$api_pid" ${web_pid:+"$web_pid"} 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for attempt in {1..40}; do
  if curl --fail --silent "http://127.0.0.1:${API_PORT:-8000}/health/ready" > /dev/null; then break; fi
  if ! kill -0 "$api_pid" 2>/dev/null; then printf 'API failed to start.\n' >&2; exit 1; fi
  sleep .25
done
curl --fail --silent "http://127.0.0.1:${API_PORT:-8000}/health/ready" > /dev/null
export API_URL="http://127.0.0.1:${API_PORT:-8000}"
export AGENTSCOPE_TOKEN_FILE="$root_dir/.local/admin-token"
export NEXT_TELEMETRY_DISABLED=1
(cd apps/web && exec node node_modules/next/dist/bin/next dev --hostname 0.0.0.0 --port "${PORT:-3000}") &
web_pid=$!
wait -n "$api_pid" "$web_pid"
