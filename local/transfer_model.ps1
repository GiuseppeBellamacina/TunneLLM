#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Transfers Ollama models from your Windows PC to the remote server via SCP.

.PARAMETER SshTarget
    SSH target in the format user@host (e.g., root@192.168.1.100)

.PARAMETER Model
    Name of the model to transfer (default: qwen2.5:14b).
    Note: ALL local models are transferred (Ollama stores them together).

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

    [string]$Model = "qwen2.5:14b",

    [int]$SshPort = 22
)

$ErrorActionPreference = "Stop"

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

$sizeMB = [math]::Round((Get-ChildItem $OllamaDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 0)

Write-Host ""
Write-Host "=== TunneLLM - Model Transfer ===" -ForegroundColor Yellow
Write-Host "    Model:       $Model"
Write-Host "    Source:      $OllamaDir"
Write-Host "    Target:      $SshTarget"
Write-Host "    Total size:  ~${sizeMB} MB"
Write-Host ""
Write-Host "    NOTE: This transfers ALL local models." -ForegroundColor Cyan
Write-Host ""

# Create remote directory
Write-Host ">>> Creating remote directory..." -ForegroundColor Cyan
ssh -p $SshPort $SshTarget "mkdir -p ~/.ollama"

# Transfer models
Write-Host ">>> Transferring models (this may take a while)..." -ForegroundColor Cyan
scp -P $SshPort -r $OllamaDir "${SshTarget}:~/.ollama/"

Write-Host ""
Write-Host "=== Transfer complete! ===" -ForegroundColor Green
Write-Host "    Verify on the server with: ollama list"
Write-Host ""
