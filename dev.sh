#!/usr/bin/env bash
# Run backend (:8400) + frontend (:5173) together. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"

trap 'kill 0' EXIT INT TERM

echo "==> Backend deps"
(cd backend && uv sync --quiet)
echo "==> Frontend deps"
(cd frontend && pnpm install --silent)

(cd backend && uv run uvicorn app.main:app --port 8400 --reload) &
(cd frontend && pnpm dev) &

sleep 2
echo ""
echo "================================================"
echo "  Open:  http://localhost:5173"
echo "  API:   http://localhost:8400/api/stats"
echo "================================================"
echo ""
wait
