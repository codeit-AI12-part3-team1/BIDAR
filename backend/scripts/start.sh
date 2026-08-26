#!/usr/bin/env bash
set -euo pipefail

# backend/scripts -> backend (실행 위치/방식과 무관하게 스크립트 자신의 절대경로 기준으로 이동)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR/.."

source .venv/bin/activate

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
