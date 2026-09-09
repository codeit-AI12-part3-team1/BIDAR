#!/usr/bin/env bash
set -euo pipefail

# backend service(uvicorn app.main:app) 프로세스를 찾아 RAM/VRAM 사용량을 초 단위로 CSV에 기록한다.
# 사용법: ./monitor_resources.sh [interval_sec] [duration_sec]
#   interval_sec: 로깅 주기 (기본 1초)
#   duration_sec: 총 실행 시간, 생략 시 Ctrl+C로 종료할 때까지 계속 실행

PROC_PATTERN="${PROC_PATTERN:-uvicorn app.main:app}"
INTERVAL="${1:-1}"
DURATION="${2:-0}"
OUT_FILE="${OUT_FILE:-resource_log_$(date +%Y%m%d_%H%M%S).csv}"

PID=$(pgrep -f "$PROC_PATTERN" | head -n1 || true)
if [[ -z "${PID:-}" ]]; then
  echo "프로세스를 찾을 수 없습니다: '$PROC_PATTERN'" >&2
  echo "backend가 실행 중인지 확인하세요 (예: uvicorn app.main:app --host 0.0.0.0 --port 8100)" >&2
  exit 1
fi

echo "모니터링 대상: PID=$PID ($(ps -o comm= -p "$PID"))"
echo "로그 파일: $OUT_FILE (주기: ${INTERVAL}s)"

echo "timestamp,pid,rss_mb,ram_used_mb,vram_proc_mb,vram_total_used_mb,vram_total_mb" > "$OUT_FILE"

START_TS=$(date +%s)
while true; do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "$(date '+%T') PID $PID 종료됨. 모니터링을 중단합니다." >&2
    break
  fi

  TS=$(date '+%Y-%m-%d %H:%M:%S')

  RSS_KB=$(ps -o rss= -p "$PID" | tr -d ' ')
  RSS_MB=$(( RSS_KB / 1024 ))

  RAM_USED_MB=$(free -m | awk '/Mem:/ {print $3}')

  # 해당 PID가 사용 중인 GPU 메모리 (MiB). 프로세스가 여러 GPU를 쓰면 합산.
  VRAM_PROC_MB=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits \
    | awk -F',' -v pid="$PID" '{gsub(/^ +| +$/,"",$1); gsub(/^ +| +$/,"",$2); if ($1==pid) sum+=$2} END {print sum+0}')

  # 참고용: GPU 전체 사용량/총량 (다중 GPU는 합산)
  VRAM_TOTAL_USED_MB=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{s+=$1} END {print s+0}')
  VRAM_TOTAL_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{s+=$1} END {print s+0}')

  echo "$TS,$PID,$RSS_MB,$RAM_USED_MB,$VRAM_PROC_MB,$VRAM_TOTAL_USED_MB,$VRAM_TOTAL_MB" >> "$OUT_FILE"

  if [[ "$DURATION" -gt 0 ]] && (( $(date +%s) - START_TS >= DURATION )); then
    echo "지정한 duration(${DURATION}s) 경과. 모니터링을 종료합니다."
    break
  fi

  sleep "$INTERVAL"
done

echo "완료: $OUT_FILE"
