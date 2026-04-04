#!/bin/bash
set -euo pipefail

# ============================================================
# Remote Server Setup — vLLM + Qwen2.5-14B-Instruct-AWQ
# Run this script once on the GPU server.
# ============================================================

MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-14B-Instruct-AWQ}"
CACHE_DIR="${HF_HOME:-$HOME/.cache/huggingface}"

echo "==> Installing vLLM and dependencies..."
pip install --upgrade pip
pip install -r "$(dirname "$0")/requirements.txt"

echo "==> Downloading model: $MODEL_ID"
huggingface-cli download "$MODEL_ID"

echo "==> Setup complete."
echo "    Model cached in: $CACHE_DIR"
echo "    Start the server with: bash remote/start_server.sh"
