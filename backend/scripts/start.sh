#!/usr/bin/env bash
set -euo pipefail

# backend/scripts -> backend (실행 위치/방식과 무관하게 스크립트 자신의 절대경로 기준으로 이동)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR/.."

source .venv/bin/activate

# gptqmodel 의 Marlin 커널 JIT 빌드가 nvcc 를 찾도록 CUDA 툴킷 경로를 명시한다
# (CUDA_HOME 미설정 시 ModuleNotFoundError: Marlin torch.ops kernels..., 실측 2026-09-02)
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"

exec uvicorn app.main:app --host 0.0.0.0 --port 8100
