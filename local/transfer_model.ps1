#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Transfers a specific Ollama model from your Windows PC to the remote server via SCP.

.PARAMETER SshTarget
    SSH target in the format user@host (e.g., root@192.168.1.100)

.PARAMETER Model
    Name of the model to transfer (default: from .env MODEL_NAME, or qwen3.6:35b).

.PARAMETER SshPort
    SSH port (default: 22)

.EXAMPLE
    .\transfer_model.ps1 -SshTarget "user@server"
    .\transfer_model.ps1 -SshTarget "user@server" -Model "llama3:8b"
    .\transfer_model.ps1 -SshTarget "user@server" -SshPort 2222
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [string]$Model = "",

    [int]$SshPort = 22
)

$ErrorActionPreference = "Stop"

# Try to read model from .env if not specified
if (-not $Model) {
    $envFile = Join-Path $PSScriptRoot ".." ".env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern '^\s*MODEL_NAME\s*=\s*(.+)' | Select-Object -First 1
        if ($match) { $Model = $match.Matches[0].Groups[1].Value.Trim('"', "'", ' ') }
    }
    if (-not $Model) { $Model = "qwen3.6:35b" }
}

# Ollama models directory on Windows
$OllamaDir = if ($env:OLLAMA_MODELS) {
    $env:OLLAMA_MODELS
} else {
    Join-Path $env:USERPROFILE ".ollama\models"
}

if (-not (Test-Path $OllamaDir)) {
    Write-Host "ERROR: Ollama models directory not found: $OllamaDir" -ForegroundColor Red
    Write-Host "Make sure Ollama is installed and the model is pulled locally:" -ForegroundColor Red
    Write-Host "  ollama pull $Model"
    exit 1
}

# ── Resolve model manifest and blobs ───────────────────────

# Model name format: name:tag or registry/namespace/name:tag
$modelParts = $Model -split ":"
$modelName = $modelParts[0]
$modelTag = if ($modelParts.Length -gt 1) { $modelParts[1] } else { "latest" }

# Ollama stores manifests at: models/manifests/registry.ollama.ai/library/<name>/<tag>
$manifestPath = Join-Path $OllamaDir "manifests" "registry.ollama.ai" "library" $modelName $modelTag

if (-not (Test-Path $manifestPath)) {
    Write-Host "ERROR: Model '$Model' not found locally." -ForegroundColor Red
    Write-Host "    Manifest expected at: $manifestPath" -ForegroundColor Red
    Write-Host "    Available models:" -ForegroundColor Yellow
    ollama list
    exit 1
}

# Parse manifest to find all blob digests
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$digests = @()
# Config digest
if ($manifest.config.digest) { $digests += $manifest.config.digest }
# Layer digests
foreach ($layer in $manifest.layers) {
    if ($layer.digest) { $digests += $layer.digest }
}

# Resolve blob file paths
$blobDir = Join-Path $OllamaDir "blobs"
$blobFiles = @()
$totalSize = 0
foreach ($digest in $digests) {
    # Blob filenames use "sha256-<hash>" format (dash instead of colon)
    $blobName = $digest -replace ":", "-"
    $blobPath = Join-Path $blobDir $blobName
    if (Test-Path $blobPath) {
        $blobFiles += $blobPath
        $totalSize += (Get-Item $blobPath).Length
    } else {
        Write-Host "WARNING: Blob not found: $blobName" -ForegroundColor Yellow
    }
}

$sizeMB = [math]::Round($totalSize / 1MB, 0)

Write-Host ""
Write-Host "=== TunneLLM - Model Transfer ===" -ForegroundColor Yellow
Write-Host "    Model:       $Model"
Write-Host "    Blobs:       $($blobFiles.Count) files"
Write-Host "    Total size:  ~${sizeMB} MB"
Write-Host "    Source:      $OllamaDir"
Write-Host "    Target:      $SshTarget"
Write-Host ""

# Create remote directories
Write-Host ">>> Creating remote directories..." -ForegroundColor Cyan
$remoteManifestDir = ".ollama/models/manifests/registry.ollama.ai/library/$modelName"
ssh -p $SshPort $SshTarget "mkdir -p ~/.ollama/models/blobs && mkdir -p ~/$remoteManifestDir"

# Transfer manifest
Write-Host ">>> Transferring manifest..." -ForegroundColor Cyan
scp -P $SshPort $manifestPath "${SshTarget}:~/${remoteManifestDir}/${modelTag}"

# Transfer blobs
Write-Host ">>> Transferring blobs ($sizeMB MB, this may take a while)..." -ForegroundColor Cyan
foreach ($blob in $blobFiles) {
    $name = Split-Path $blob -Leaf
    Write-Host "    $name" -ForegroundColor Gray
    scp -P $SshPort $blob "${SshTarget}:~/.ollama/models/blobs/"
}

Write-Host ""
Write-Host "=== Transfer complete! ===" -ForegroundColor Green
Write-Host "    Verify on the server with: ollama list"
Write-Host ""
