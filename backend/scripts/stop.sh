#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="bidar-backend"

# systemd에 등록된 배포 서버라면 systemctl로 종료한다.
# (start.sh가 exec로 uvicorn을 실행하므로 PID가 그대로 uvicorn 프로세스다 ->
#  systemctl stop이 SIGTERM을 uvicorn에 직접 보내 정상 종료된다)
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    echo "systemd 서비스로 종료합니다: ${SERVICE_NAME}"
    sudo systemctl stop "${SERVICE_NAME}"
    exit 0
fi

# systemd가 없는 로컬/개발 환경: start.sh로 백그라운드에 띄운 uvicorn을 직접 종료한다.
echo "systemd 서비스가 없어, 실행 중인 uvicorn 프로세스를 직접 종료합니다."
PIDS="$(pgrep -f 'uvicorn app\.main:app' || true)"

if [[ -z "$PIDS" ]]; then
    echo "실행 중인 서버 프로세스를 찾지 못했습니다."
    exit 0
fi

echo "종료 대상 PID: $PIDS"
kill $PIDS
