#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Downloads Ollama for Linux on Windows and deploys it to a remote server via SCP.

.DESCRIPTION
    Since the remote server has no internet (SSH-only), this script:
    1. Downloads the Ollama Linux binary archive on your Windows machine
    2. Transfers it to the remote server via SCP
    3. Transfers the remote setup script
    4. Optionally runs the installer on the server via SSH

.PARAMETER SshTarget
    SSH target in the format user@host (e.g., root@192.168.1.100)

.PARAMETER Arch
    Target architecture: amd64 or arm64 (default: amd64)

.PARAMETER SshPort
    SSH port (default: 22)

.PARAMETER RemoteDir
    Remote directory to upload files to (default: ~/ollama-server)

.PARAMETER SkipInstall
    If set, only downloads and transfers files without running the installer

.PARAMETER IncludeROCm
    Also download the AMD ROCm GPU support package

.EXAMPLE
    .\download_and_deploy.ps1 -SshTarget "user@server"
    .\download_and_deploy.ps1 -SshTarget "user@server" -Arch arm64
    .\download_and_deploy.ps1 -SshTarget "user@server" -SkipInstall
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [ValidateSet("amd64", "arm64")]
    [string]$Arch = "amd64",

    [int]$SshPort = 22,

    [string]$RemoteDir = "~/ollama-server",

    [switch]$SkipInstall,

    [switch]$IncludeROCm
)

$ErrorActionPreference = "Stop"

$DownloadDir = Join-Path $PSScriptRoot "ollama-download"
$BaseUrl = "https://ollama.com/download"

# ── Download helpers ────────────────────────────────────────

function Download-File {
    param([string]$Url, [string]$OutFile)
    Write-Host ">>> Downloading: $Url" -ForegroundColor Cyan
    Write-Host "    -> $OutFile"
    
    # Use TLS 1.2+
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

    $ProgressPreference = 'SilentlyContinue'  # Speeds up Invoke-WebRequest
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
    
    $size = (Get-Item $OutFile).Length / 1MB
    Write-Host "    Downloaded: $([math]::Round($size, 1)) MB" -ForegroundColor Green
}

function Test-UrlExists {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# ── Main ────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== TunneLLM - Ollama Offline Deployer ===" -ForegroundColor Yellow
Write-Host "    Target:  $SshTarget (port $SshPort)" 
Write-Host "    Arch:    $Arch"
Write-Host ""

# Create download directory
if (-not (Test-Path $DownloadDir)) {
    New-Item -ItemType Directory -Path $DownloadDir | Out-Null
}

# Try .tar.zst first, fall back to .tgz
$archiveFile = $null
$zstUrl = "$BaseUrl/ollama-linux-${Arch}.tar.zst"
$tgzUrl = "$BaseUrl/ollama-linux-${Arch}.tgz"

Write-Host ">>> Checking for .tar.zst archive..." -ForegroundColor Cyan
if (Test-UrlExists $zstUrl) {
    $archiveFile = Join-Path $DownloadDir "ollama-linux-${Arch}.tar.zst"
    Download-File -Url $zstUrl -OutFile $archiveFile
    Write-Host "    NOTE: The server needs 'zstd' to extract this. If not available, re-run or use .tgz." -ForegroundColor Yellow
} else {
    Write-Host "    .tar.zst not available, falling back to .tgz" -ForegroundColor Yellow
    $archiveFile = Join-Path $DownloadDir "ollama-linux-${Arch}.tgz"
    Download-File -Url $tgzUrl -OutFile $archiveFile
}

# Optionally download ROCm (AMD GPU) package
if ($IncludeROCm) {
    $rocmFile = Join-Path $DownloadDir "ollama-linux-${Arch}-rocm.tar.zst"
    $rocmUrl = "$BaseUrl/ollama-linux-${Arch}-rocm.tar.zst"
    
    if (Test-UrlExists $rocmUrl) {
        Download-File -Url $rocmUrl -OutFile $rocmFile
    } else {
        $rocmTgz = "$BaseUrl/ollama-linux-${Arch}-rocm.tgz"
        $rocmFile = Join-Path $DownloadDir "ollama-linux-${Arch}-rocm.tgz"
        Download-File -Url $rocmTgz -OutFile $rocmFile
    }
}

Write-Host ""
Write-Host ">>> Download complete. Files in: $DownloadDir" -ForegroundColor Green
Get-ChildItem $DownloadDir | ForEach-Object {
    $sizeMB = [math]::Round($_.Length / 1MB, 1)
    Write-Host "    $($_.Name)  ($sizeMB MB)"
}

# ── Transfer to server via SCP ──────────────────────────────

Write-Host ""
Write-Host ">>> Creating remote directory: $RemoteDir" -ForegroundColor Cyan
ssh -p $SshPort $SshTarget "mkdir -p $RemoteDir"

Write-Host ">>> Transferring Ollama archive..." -ForegroundColor Cyan
scp -P $SshPort $archiveFile "${SshTarget}:${RemoteDir}/"

if ($IncludeROCm -and (Test-Path (Join-Path $DownloadDir "ollama-linux-${Arch}-rocm.*"))) {
    Write-Host ">>> Transferring ROCm package..." -ForegroundColor Cyan
    $rocmFiles = Get-ChildItem $DownloadDir -Filter "ollama-linux-${Arch}-rocm.*"
    foreach ($f in $rocmFiles) {
        scp -P $SshPort $f.FullName "${SshTarget}:${RemoteDir}/"
    }
}

# Transfer remote scripts
$remoteScriptsDir = Join-Path $PSScriptRoot ".." "remote"
Write-Host ">>> Transferring setup scripts..." -ForegroundColor Cyan
scp -P $SshPort -r $remoteScriptsDir/* "${SshTarget}:${RemoteDir}/"

# ── Install on server ──────────────────────────────────────

if (-not $SkipInstall) {
    Write-Host ""
    Write-Host ">>> Running installer on remote server..." -ForegroundColor Cyan
    
    $archiveName = Split-Path $archiveFile -Leaf
    ssh -p $SshPort $SshTarget "cd $RemoteDir && OLLAMA_ARCHIVE='$RemoteDir/$archiveName' bash setup.sh"
    
    Write-Host ""
    Write-Host "=== Installation complete! ===" -ForegroundColor Green
    Write-Host "    Next steps on the server:" -ForegroundColor Yellow
    Write-Host "    1. Transfer a model (see below)"
    Write-Host "    2. Start Ollama:  cd $RemoteDir && bash start_server.sh"
    Write-Host ""
    Write-Host "    To transfer a model from this machine:" -ForegroundColor Yellow
    Write-Host "    ollama pull qwen2.5:14b"
    Write-Host "    .\transfer_model.ps1 -SshTarget $SshTarget"
} else {
    Write-Host ""
    Write-Host "=== Transfer complete (install skipped) ===" -ForegroundColor Green
    Write-Host "    To install on the server:" -ForegroundColor Yellow
    $archiveName = Split-Path $archiveFile -Leaf
    Write-Host "    ssh $SshTarget"
    Write-Host "    cd $RemoteDir"
    Write-Host "    OLLAMA_ARCHIVE='$RemoteDir/$archiveName' bash setup.sh"
}

Write-Host ""
