#!/usr/bin/env bash
# ── Local development: backend (FastAPI :8000) + frontend (Vite :5173) ──
# The Vite dev server proxies /api to the backend.
set -euo pipefail
cd "$(dirname "$0")/.."

# backend venv (created on first run)
if [ ! -d backend/.venv ]; then
  echo "── creating backend virtualenv…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

echo "── backend  → http://localhost:8000  (API at /api/*)"
echo "── frontend → http://localhost:5173  (dev proxy → :8000)"
echo "── tip: full UI is also served directly at http://localhost:8000 after 'npm run build'"

(cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACK=$!

(cd frontend && npm run dev) &
FRONT=$!

trap "kill $BACK $FRONT 2>/dev/null || true" EXIT
wait
