#!/bin/bash
set -euo pipefail

# ============================================================
# Remote Server Setup — Ollama (Offline Installation)
#
# Installs Ollama from a local archive transferred via SCP.
# Works completely offline. Supports both:
#   - Root/sudo install (system-wide, /usr/local/)
#   - User-local install (no root needed, ~/.local/)
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

# ── Determine install mode ──────────────────────────────────

SUDO=
USER_LOCAL=false

if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        USER_LOCAL=true
    fi
fi

if [ "$USER_LOCAL" = true ]; then
    # User-local install (cluster / no root)
    OLLAMA_INSTALL_DIR="$HOME/.local"
    BINDIR="$HOME/.local/bin"
    echo "==> User-local install (no root/sudo detected)"
else
    # System-wide install
    for BINDIR in /usr/local/bin /usr/bin /bin; do
        echo "$PATH" | grep -q "$BINDIR" && break || continue
    done
    OLLAMA_INSTALL_DIR=$(dirname "${BINDIR}")
    echo "==> System-wide install"
fi

# ── Clean old installation ──────────────────────────────────

if [ -d "$OLLAMA_INSTALL_DIR/lib/ollama" ]; then
    echo "==> Cleaning up old Ollama installation at $OLLAMA_INSTALL_DIR/lib/ollama"
    $SUDO rm -rf "$OLLAMA_INSTALL_DIR/lib/ollama"
fi

# ── Extract archive ─────────────────────────────────────────

echo "==> Installing Ollama from: $OLLAMA_ARCHIVE"
echo "    Install directory: $OLLAMA_INSTALL_DIR"

if [ "$USER_LOCAL" = true ]; then
    mkdir -p "$BINDIR"
    mkdir -p "$OLLAMA_INSTALL_DIR/lib/ollama"
else
    $SUDO install -o0 -g0 -m755 -d "$BINDIR"
    $SUDO install -o0 -g0 -m755 -d "$OLLAMA_INSTALL_DIR/lib/ollama"
fi

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

if [ -f "$OLLAMA_INSTALL_DIR/bin/ollama" ] && [ "$OLLAMA_INSTALL_DIR/bin/ollama" != "$BINDIR/ollama" ]; then
    echo "==> Creating symlink: $BINDIR/ollama"
    $SUDO ln -sf "$OLLAMA_INSTALL_DIR/bin/ollama" "$BINDIR/ollama"
elif [ -f "$OLLAMA_INSTALL_DIR/ollama" ] && [ ! -f "$BINDIR/ollama" ]; then
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

# ── Configure systemd service (only for system-wide install) ─

if [ "$USER_LOCAL" = false ]; then
    configure_systemd() {
        if ! command -v systemctl >/dev/null 2>&1; then
            return
        fi

        if ! id ollama >/dev/null 2>&1; then
            echo "==> Creating ollama user..."
            $SUDO useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama
        fi

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
                echo "==> Enabling ollama service..."
                $SUDO systemctl daemon-reload
                $SUDO systemctl enable ollama
                ;;
            *)
                echo "    NOTE: systemd not running. Use start_server.sh to run Ollama manually."
                ;;
        esac
    }
    configure_systemd
else
    echo "==> Skipping systemd setup (user-local install)."
fi

# ── Add to PATH hint ───────────────────────────────────────

if [ "$USER_LOCAL" = true ]; then
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        echo ""
        echo "==> IMPORTANT: Add ~/.local/bin to your PATH."
        echo "    Run this now and add it to your ~/.bashrc:"
        echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
        # Add to .bashrc if not already there
        if ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
            echo "    (Added automatically to ~/.bashrc)"
        fi
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

# ── Verify installation ────────────────────────────────────

echo ""
if command -v ollama >/dev/null 2>&1; then
    echo "==> Ollama installed successfully: $(ollama --version 2>/dev/null || echo 'version unknown')"
else
    export PATH="$BINDIR:$PATH"
    if command -v ollama >/dev/null 2>&1; then
        echo "==> Ollama installed successfully: $(ollama --version 2>/dev/null || echo 'version unknown')"
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
echo "       .\\transfer_model.ps1 -SshTarget user@this-server"
echo "    2. Start Ollama:"
echo "       bash start_server.sh"
