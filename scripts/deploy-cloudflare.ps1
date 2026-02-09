<#
.SYNOPSIS
    AMTTP Platform Deployment Script for Windows

.DESCRIPTION
    Deploys the AMTTP platform with Cloudflare Tunnel for secure public access.
    Handles building, configuration, and starting all services.

.PARAMETER Action
    The action to perform: deploy, start, stop, status, logs, clean

.PARAMETER TunnelToken
    Cloudflare Tunnel token (can also be set via CLOUDFLARE_TUNNEL_TOKEN env var)

.EXAMPLE
    .\deploy-cloudflare.ps1 -Action deploy -TunnelToken "eyJhIjoiY..."

.EXAMPLE
    .\deploy-cloudflare.ps1 -Action status
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("deploy", "start", "stop", "status", "logs", "clean", "build")]
    [string]$Action = "deploy",
    
    [Parameter(Mandatory=$false)]
    [string]$TunnelToken = $env:CLOUDFLARE_TUNNEL_TOKEN,
    
    [Parameter(Mandatory=$false)]
    [switch]$WithDev,
    
    [Parameter(Mandatory=$false)]
    [string]$LogTail = "100"
)

$ErrorActionPreference = "Stop"

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = Get-Location }

$ComposeFile = Join-Path $ProjectRoot "docker-compose.cloudflare.yml"
$EnvFile = Join-Path $ProjectRoot ".env.production"

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "→ $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Test-DockerRunning {
    try {
        docker info | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-DockerCompose {
    try {
        docker compose version | Out-Null
        return $true
    } catch {
        return $false
    }
}

function New-EnvFile {
    Write-Step "Creating production environment file..."
    
    $envContent = @"
# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Production Environment Configuration
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# ═══════════════════════════════════════════════════════════════════════════════

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=$TunnelToken

# MongoDB
MONGO_ROOT_USER=admin
MONGO_ROOT_PASSWORD=$(New-Guid).Guid.Substring(0,16)
MONGODB_URI=mongodb://admin:$((New-Guid).Guid.Substring(0,16))@mongo:27017/amttp?authSource=admin

# Redis
REDIS_URL=redis://redis:6379

# Memgraph
MEMGRAPH_PASSWORD=$(New-Guid).Guid.Substring(0,16)

# MinIO
MINIO_ROOT_USER=amttp_admin
MINIO_ROOT_PASSWORD=$(New-Guid).Guid.Substring(0,16)

# Ethereum (Update with your RPC endpoint)
ETH_RPC_URL=https://sepolia.infura.io/v3/YOUR_INFURA_KEY
CHAIN_ID=11155111

# Contract Addresses (Update after deployment)
AMTTP_CORE_ADDRESS=
AMTTP_NFT_ADDRESS=
AMTTP_ZKNAF_ADDRESS=

# Application
NODE_ENV=production
LOG_LEVEL=info
"@
    
    Set-Content -Path $EnvFile -Value $envContent
    Write-Step "Environment file created at: $EnvFile"
    Write-Warning "Please update ETH_RPC_URL and contract addresses in $EnvFile"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main Actions
# ═══════════════════════════════════════════════════════════════════════════════

function Invoke-Build {
    Write-Header "Building AMTTP Platform"
    
    Write-Step "Building Docker images..."
    docker compose -f $ComposeFile build --no-cache
    
    Write-Step "Build complete!"
}

function Invoke-Deploy {
    Write-Header "Deploying AMTTP Platform with Cloudflare Tunnel"
    
    # Validate prerequisites
    if (-not (Test-DockerRunning)) {
        Write-Error "Docker is not running. Please start Docker Desktop."
        exit 1
    }
    
    if (-not (Test-DockerCompose)) {
        Write-Error "Docker Compose is not available."
        exit 1
    }
    
    # Check tunnel token
    if ([string]::IsNullOrEmpty($TunnelToken)) {
        Write-Error "Cloudflare Tunnel token is required."
        Write-Host ""
        Write-Host "To get a tunnel token:" -ForegroundColor Yellow
        Write-Host "  1. Go to https://one.dash.cloudflare.com" -ForegroundColor Yellow
        Write-Host "  2. Navigate to: Zero Trust → Networks → Tunnels" -ForegroundColor Yellow
        Write-Host "  3. Create a new tunnel or use existing one" -ForegroundColor Yellow
        Write-Host "  4. Copy the tunnel token" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Then run:" -ForegroundColor Cyan
        Write-Host "  .\deploy-cloudflare.ps1 -Action deploy -TunnelToken 'your-token-here'" -ForegroundColor Cyan
        exit 1
    }
    
    # Create env file if not exists
    if (-not (Test-Path $EnvFile)) {
        New-EnvFile
    }
    
    # Update tunnel token in env
    $envContent = Get-Content $EnvFile -Raw
    $envContent = $envContent -replace 'CLOUDFLARE_TUNNEL_TOKEN=.*', "CLOUDFLARE_TUNNEL_TOKEN=$TunnelToken"
    Set-Content -Path $EnvFile -Value $envContent
    
    Write-Step "Building Docker images..."
    docker compose -f $ComposeFile --env-file $EnvFile build
    
    Write-Step "Starting services..."
    $profiles = ""
    if ($WithDev) {
        $profiles = "--profile dev"
    }
    
    docker compose -f $ComposeFile --env-file $EnvFile $profiles up -d
    
    Write-Step "Waiting for services to be healthy..."
    Start-Sleep -Seconds 10
    
    Invoke-Status
    
    Write-Header "Deployment Complete!"
    Write-Host "Your AMTTP platform is now accessible via Cloudflare Tunnel." -ForegroundColor Green
    Write-Host ""
    Write-Host "Configure your Cloudflare Tunnel public hostname to point to this container." -ForegroundColor Yellow
    Write-Host "The tunnel will route traffic to the internal nginx on port 80." -ForegroundColor Yellow
}

function Invoke-Start {
    Write-Header "Starting AMTTP Platform"
    
    if (-not (Test-Path $EnvFile)) {
        Write-Error "Environment file not found. Run 'deploy' first."
        exit 1
    }
    
    $profiles = ""
    if ($WithDev) {
        $profiles = "--profile dev"
    }
    
    docker compose -f $ComposeFile --env-file $EnvFile $profiles up -d
    
    Write-Step "Services starting..."
    Start-Sleep -Seconds 5
    Invoke-Status
}

function Invoke-Stop {
    Write-Header "Stopping AMTTP Platform"
    
    docker compose -f $ComposeFile down
    
    Write-Step "All services stopped."
}

function Invoke-Status {
    Write-Header "AMTTP Platform Status"
    
    docker compose -f $ComposeFile ps -a
    
    Write-Host ""
    Write-Step "Checking health endpoints..."
    
    try {
        $health = docker exec amttp-platform curl -sf http://localhost/health 2>$null
        if ($health) {
            Write-Host "  Platform Health: " -NoNewline
            Write-Host "HEALTHY" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Platform Health: " -NoNewline
        Write-Host "STARTING..." -ForegroundColor Yellow
    }
}

function Invoke-Logs {
    Write-Header "AMTTP Platform Logs"
    
    docker compose -f $ComposeFile logs --tail=$LogTail -f
}

function Invoke-Clean {
    Write-Header "Cleaning AMTTP Platform"
    
    Write-Warning "This will remove all containers, volumes, and images!"
    $confirm = Read-Host "Are you sure? (yes/no)"
    
    if ($confirm -eq "yes") {
        Write-Step "Stopping containers..."
        docker compose -f $ComposeFile down -v --rmi all
        
        Write-Step "Pruning Docker resources..."
        docker system prune -f
        
        Write-Step "Cleanup complete."
    } else {
        Write-Step "Cleanup cancelled."
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║           AMTTP Platform - Cloudflare Deployment                  ║" -ForegroundColor Magenta
Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Magenta

switch ($Action) {
    "build"   { Invoke-Build }
    "deploy"  { Invoke-Deploy }
    "start"   { Invoke-Start }
    "stop"    { Invoke-Stop }
    "status"  { Invoke-Status }
    "logs"    { Invoke-Logs }
    "clean"   { Invoke-Clean }
}

Write-Host ""
