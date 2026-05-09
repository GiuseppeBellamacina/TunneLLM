#!/bin/bash
set -euo pipefail

# ============================================================
# Start Ollama server
# Bound to 127.0.0.1 only (access via SSH tunnel)
# ============================================================

MODEL="${MODEL:-qwen2.5:14b}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_HOST

echo "==> Starting Ollama server on $OLLAMA_HOST"
echo "    Model: $MODEL"

# Start Ollama serve in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "==> Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if curl -s "http://$OLLAMA_HOST/" >/dev/null 2>&1; then
        echo "==> Ollama is ready."
        break
    fi
    sleep 1
done

# Load the model (keep it warm in memory)
echo "==> Loading model: $MODEL"
ollama run "$MODEL" "" 2>/dev/null || true

echo "==> Model loaded. Ollama is serving on $OLLAMA_HOST"
echo "    PID: $OLLAMA_PID"
echo "    Stop with: kill $OLLAMA_PID"

# Keep in foreground
wait $OLLAMA_PID
