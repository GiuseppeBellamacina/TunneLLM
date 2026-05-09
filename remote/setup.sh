#!/bin/bash
set -euo pipefail

# ============================================================
# Remote Server Setup — Ollama (Offline Installation)
#
# This script installs Ollama from a local archive transferred
# via SCP. It mirrors the official install.sh logic but works
# completely offline.
#
# Usage:
#   OLLAMA_ARCHIVE=/path/to/ollama-linux-amd64.tgz bash setup.sh
#
# The archive can be .tgz or .tar.zst (requires zstd on server).
#
# From Windows, use download_and_deploy.ps1 which handles
# everything automatically.
# ============================================================

OLLAMA_ARCHIVE="${OLLAMA_ARCHIVE:-}"

if [ -z "$OLLAMA_ARCHIVE" ]; then
    echo "ERROR: OLLAMA_ARCHIVE not set."
    echo ""
    echo "Usage: OLLAMA_ARCHIVE=/path/to/ollama-linux-amd64.tgz bash setup.sh"
    echo ""
    echo "Get the archive on your local machine (with internet):"
    echo "  curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz -o ollama.tgz"
    echo "  scp ollama.tgz user@server:~/"
    exit 1
fi

if [ ! -f "$OLLAMA_ARCHIVE" ]; then
    echo "ERROR: Archive not found: $OLLAMA_ARCHIVE"
    exit 1
fi

# ── Determine install directory ─────────────────────────────

SUDO=
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "WARNING: Not running as root and sudo not available."
        echo "         Installing to user-local directory."
    fi
fi

# Find a suitable bin directory in PATH
for BINDIR in /usr/local/bin /usr/bin /bin; do
    echo "$PATH" | grep -q "$BINDIR" && break || continue
done
OLLAMA_INSTALL_DIR=$(dirname "${BINDIR}")

# ── Clean old installation ──────────────────────────────────

if [ -d "$OLLAMA_INSTALL_DIR/lib/ollama" ]; then
    echo "==> Cleaning up old Ollama installation at $OLLAMA_INSTALL_DIR/lib/ollama"
    $SUDO rm -rf "$OLLAMA_INSTALL_DIR/lib/ollama"
fi

# ── Extract archive ─────────────────────────────────────────

echo "==> Installing Ollama from: $OLLAMA_ARCHIVE"
echo "    Install directory: $OLLAMA_INSTALL_DIR"

$SUDO install -o0 -g0 -m755 -d "$BINDIR"
$SUDO install -o0 -g0 -m755 -d "$OLLAMA_INSTALL_DIR/lib/ollama"

case "$OLLAMA_ARCHIVE" in
    *.tar.zst)
        if ! command -v zstd >/dev/null 2>&1; then
            echo "ERROR: .tar.zst archive requires zstd to extract."
            echo "       Install zstd or use the .tgz archive instead."
            exit 1
        fi
        zstd -d < "$OLLAMA_ARCHIVE" | $SUDO tar -xf - -C "$OLLAMA_INSTALL_DIR"
        ;;
    *.tgz|*.tar.gz)
        $SUDO tar -xzf "$OLLAMA_ARCHIVE" -C "$OLLAMA_INSTALL_DIR"
        ;;
    *)
        echo "ERROR: Unsupported archive format. Use .tgz or .tar.zst"
        exit 1
        ;;
esac

# ── Create symlink if needed ────────────────────────────────

if [ "$OLLAMA_INSTALL_DIR/bin/ollama" != "$BINDIR/ollama" ]; then
    echo "==> Creating symlink: $BINDIR/ollama"
    $SUDO ln -sf "$OLLAMA_INSTALL_DIR/ollama" "$BINDIR/ollama"
fi

# ── Install ROCm package if present ─────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROCM_ARCHIVE=""
for f in "$SCRIPT_DIR"/ollama-linux-*-rocm.tar.zst "$SCRIPT_DIR"/ollama-linux-*-rocm.tgz; do
    if [ -f "$f" ]; then
        ROCM_ARCHIVE="$f"
        break
    fi
done

if [ -n "$ROCM_ARCHIVE" ]; then
    echo "==> Installing ROCm GPU support from: $ROCM_ARCHIVE"
    case "$ROCM_ARCHIVE" in
        *.tar.zst) zstd -d < "$ROCM_ARCHIVE" | $SUDO tar -xf - -C "$OLLAMA_INSTALL_DIR" ;;
        *.tgz|*.tar.gz) $SUDO tar -xzf "$ROCM_ARCHIVE" -C "$OLLAMA_INSTALL_DIR" ;;
    esac
fi

# ── Configure systemd service (optional) ────────────────────

configure_systemd() {
    if ! command -v systemctl >/dev/null 2>&1; then
        return
    fi

    if ! id ollama >/dev/null 2>&1; then
        echo "==> Creating ollama user..."
        $SUDO useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama
    fi

    # Add to GPU groups if they exist
    for GROUP in render video; do
        if getent group "$GROUP" >/dev/null 2>&1; then
            $SUDO usermod -a -G "$GROUP" ollama 2>/dev/null || true
        fi
    done

    echo "==> Creating ollama systemd service..."
    cat <<EOF | $SUDO tee /etc/systemd/system/ollama.service >/dev/null
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=$BINDIR/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=$PATH"
Environment="OLLAMA_HOST=127.0.0.1:11434"

[Install]
WantedBy=default.target
EOF

    SYSTEMCTL_RUNNING="$(systemctl is-system-running 2>/dev/null || true)"
    case $SYSTEMCTL_RUNNING in
        running|degraded)
            echo "==> Enabling ollama service (not starting — use start_server.sh)..."
            $SUDO systemctl daemon-reload
            $SUDO systemctl enable ollama
            ;;
        *)
            echo "    NOTE: systemd not running. Use start_server.sh to run Ollama manually."
            ;;
    esac
}

configure_systemd

# ── Verify installation ────────────────────────────────────

echo ""
if command -v ollama >/dev/null 2>&1; then
    echo "==> Ollama installed successfully: $(ollama --version 2>/dev/null || echo 'version unknown')"
else
    export PATH="$BINDIR:$PATH"
    if command -v ollama >/dev/null 2>&1; then
        echo "==> Ollama installed successfully: $(ollama --version 2>/dev/null || echo 'version unknown')"
        echo "    NOTE: Add to your PATH: export PATH=$BINDIR:\$PATH"
    else
        echo "ERROR: Ollama binary not found after installation."
        exit 1
    fi
fi

echo ""
echo "==> Setup complete."
echo "    Ollama installed to: $OLLAMA_INSTALL_DIR"
echo "    Binary: $BINDIR/ollama"
echo ""
echo "    Next steps:"
echo "    1. Transfer a model from your local machine:"
echo "       bash local/transfer_model.sh qwen2.5:14b user@this-server"
echo "    2. Start Ollama:"
echo "       bash start_server.sh"
