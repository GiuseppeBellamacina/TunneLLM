#!/bin/bash
#SBATCH --job-name=training
#SBATCH --output=logs/ollama-%j.log
#SBATCH --error=logs/ollama-%j.log
#SBATCH --gres=gpu:1 --gres=shard:22528
#SBATCH --mem=48G
#SBATCH --cpus-per-task=8
#SBATCH --account=dl-course-q2
#SBATCH --partition=dl-course-q2
#SBATCH --qos=gpu-xlarge

# ============================================================
# SLURM Job — Ollama Server on GPU node
#
# Avvia Ollama su un nodo GPU del cluster e scrive le
# informazioni di connessione in ~/ollama-server/node_info.txt
# così il proxy locale sa dove connettersi.
#
# Usage:
#   sbatch ollama_job.sh                   # modello default
#   sbatch ollama_job.sh qwen3.6:35b       # modello specifico
#
# Per cambiare QoS/risorse, modifica le direttive #SBATCH sopra
# oppure usa override da CLI:
#   sbatch --qos=gpu-large --time=06:00:00 ollama_job.sh
#
# Il job scrive il file ~/ollama-server/node_info.txt con:
#   NODE=<hostname del nodo assegnato>
#   PORT=11434
# Il proxy locale legge REMOTE_HOST dal .env — impostalo
# al nodo assegnato dopo aver lanciato il job.
# ============================================================

set -euo pipefail

MODEL="${1:-qwen3.6:35b}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
INFO_DIR="$HOME/ollama-server"
INFO_FILE="$INFO_DIR/node_info.txt"

# Ensure PATH includes user-local install
export PATH="$HOME/.local/bin:$PATH"

# Disable proxy for local connections (clusters often have http_proxy set)
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY

# Ensure Ollama is installed
if ! command -v ollama >/dev/null 2>&1; then
    echo "ERROR: ollama not found in PATH."
    echo "       Run setup.sh first to install Ollama."
    exit 1
fi

# Get the node hostname
NODE_NAME=$(hostname)

# Bind to 0.0.0.0 so the login node can reach us via internal network
export OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}"

# Write connection info
mkdir -p "$INFO_DIR"
cat > "$INFO_FILE" <<EOF
NODE=${NODE_NAME}
PORT=${OLLAMA_PORT}
MODEL=${MODEL}
JOB_ID=${SLURM_JOB_ID}
EOF

echo "============================================"
echo "  Ollama SLURM Job"
echo "============================================"
echo "  Job ID:    ${SLURM_JOB_ID}"
echo "  Node:      ${NODE_NAME}"
echo "  GPU:       $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'unknown')"
echo "  VRAM:      $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo 'unknown')"
echo "  Ollama:    ${NODE_NAME}:${OLLAMA_PORT}"
echo "  Model:     ${MODEL}"
echo "  Info file: ${INFO_FILE}"
echo ""
echo "  Sul tuo PC, imposta nel .env:"
echo "    REMOTE_HOST=${NODE_NAME}"
echo "============================================"
echo ""

# Start Ollama server
echo "==> Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "==> Waiting for Ollama to start..."
for i in $(seq 1 60); do
    if curl --noproxy '*' -s "http://localhost:${OLLAMA_PORT}/" >/dev/null 2>&1; then
        echo "==> Ollama is ready on ${NODE_NAME}:${OLLAMA_PORT}"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: Ollama failed to start within 60 seconds."
        kill $OLLAMA_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Pre-load the model into GPU memory
echo "==> Loading model: ${MODEL}"
if ollama run "$MODEL" "" 2>/dev/null; then
    echo "==> Model loaded successfully."
else
    echo "WARNING: Could not pre-load model. It will load on first request."
fi

echo ""
echo "==> Ollama is serving. Job will run until time limit or cancellation."
echo "    To stop: scancel ${SLURM_JOB_ID}"
echo ""

# Keep running until SLURM kills us
wait $OLLAMA_PID
