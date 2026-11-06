#!/usr/bin/env bash
# Starts the real app for the end-to-end tests: fresh temporary database, an admin
# account, and the backend serving the built frontend (npm run build first).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
backend="$here/../../backend"
dir="$(mktemp -d)"
export DATABASE_URL="sqlite:///$dir/e2e.db"
export STATIC_DIR="$here/../dist"
export APP_ENV=dev
# Reviews get fixed answers; no LLM provider is called (test strategy §6)
export LLM_FAKE=1
# Fixed listings, prices and rates; no price provider is called (test strategy §6)
export PRICE_FAKE=1
# No scheduled price update at an unpredictable moment; the backend tests cover it
export PRICE_SCHEDULER=false
export APP_SECRET_KEY="e2e secret for API keys"
cd "$backend"
python -m yap.cli migrate
echo "${E2E_ADMIN_PASSWORD:-admin password 1}" | python -m yap.cli create-admin admin --password-stdin
exec python -m uvicorn --factory yap.api.app:create_app_from_env --port "${E2E_PORT:-8790}"
