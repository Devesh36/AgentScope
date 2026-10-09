#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.local/cache/uv}"
export npm_config_cache="${npm_config_cache:-$PWD/.local/cache/npm}"
uv venv --allow-existing .venv --python python3
uv pip sync apps/api/requirements.txt --python .venv/bin/python
uv pip install --python .venv/bin/python --no-deps -e packages/python-sdk
uv pip install --python .venv/bin/python --no-deps -e .
npm --prefix apps/web ci --no-audit --no-fund
(cd apps/api && ../../.venv/bin/alembic upgrade head)
