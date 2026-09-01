#!/usr/bin/env bash
set -euo pipefail

# backend/scripts -> backend (실행 위치/방식과 무관하게 스크립트 자신의 절대경로 기준으로 이동)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
BACKEND_DIR="$SCRIPT_DIR/.."
REPO_ROOT="$BACKEND_DIR/.."

SERVICE_NAME="bidar-backend"

echo "==> 최신 코드 받는 중"
git -C "$REPO_ROOT" pull

echo "==> 의존성 설치 (requirements.txt의 -e ../ai 로 ai 패키지도 같이 설치됨)"
cd "$BACKEND_DIR"
source .venv/bin/activate
pip install -r requirements.txt
deactivate

echo "==> 서비스 재시작: ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "==> 상태 확인"
sudo systemctl status "${SERVICE_NAME}" --no-pager -l