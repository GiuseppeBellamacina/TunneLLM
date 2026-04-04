#!/bin/bash
set -euo pipefail

# ============================================================
# Start vLLM OpenAI-compatible server
# Bound to 127.0.0.1 only (access via SSH tunnel)
# ============================================================

MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-14B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8000}"
GPU_MEM="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
API_KEY="${VLLM_API_KEY:-}"

CMD=(
    vllm serve "$MODEL_ID"
    --host 127.0.0.1
    --port "$PORT"
    --dtype auto
    --gpu-memory-utilization "$GPU_MEM"
    --max-model-len "$MAX_MODEL_LEN"
    --trust-remote-code
)

if [ -n "$API_KEY" ]; then
    CMD+=(--api-key "$API_KEY")
fi

echo "==> Starting vLLM server on 127.0.0.1:$PORT"
echo "    Model: $MODEL_ID"
echo "    GPU mem utilization: $GPU_MEM"
echo "    Max model length: $MAX_MODEL_LEN"

exec "${CMD[@]}"
