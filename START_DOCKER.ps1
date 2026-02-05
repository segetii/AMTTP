# ============================================================================
# AMTTP Full Stack Docker Launch Script
# ============================================================================
# This script builds and starts all AMTTP services in Docker containers
# including ngrok for public web exposure.
# ============================================================================

param(
    [switch]$Build,
    [switch]$Down,
    [switch]$Logs,
    [switch]$Status,
    [string]$NgrokToken
)

$ErrorActionPreference = "Stop"
$ComposeFile = "docker-compose.full.yml"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AMTTP Full Stack Docker Manager" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
} catch {
    Write-Host "ERROR: Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Set ngrok token if provided
if ($NgrokToken) {
    $env:NGROK_AUTHTOKEN = $NgrokToken
    Write-Host "Using provided ngrok token" -ForegroundColor Green
}

# Handle commands
if ($Down) {
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    docker-compose -f $ComposeFile down
    Write-Host "All services stopped." -ForegroundColor Green
    exit 0
}

if ($Status) {
    Write-Host "Service Status:" -ForegroundColor Yellow
    docker-compose -f $ComposeFile ps
    Write-Host ""
    Write-Host "Getting ngrok tunnel URLs..." -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 5
        Write-Host ""
        Write-Host "PUBLIC URLS:" -ForegroundColor Green
        foreach ($tunnel in $response.tunnels) {
            Write-Host "  $($tunnel.name): $($tunnel.public_url)" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "  ngrok API not available. Tunnels may still be starting..." -ForegroundColor Yellow
    }
    exit 0
}

if ($Logs) {
    Write-Host "Following logs (Ctrl+C to stop)..." -ForegroundColor Yellow
    docker-compose -f $ComposeFile logs -f
    exit 0
}

# Default: Start services
if ($Build) {
    Write-Host "Building all Docker images..." -ForegroundColor Yellow
    docker-compose -f $ComposeFile build
}

Write-Host "Starting all services..." -ForegroundColor Yellow
docker-compose -f $ComposeFile up -d

Write-Host ""
Write-Host "Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AMTTP Services Started!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "LOCAL URLS:" -ForegroundColor Yellow
Write-Host "  Flutter App:     http://localhost:8889" -ForegroundColor White
Write-Host "  War Room:        http://localhost:3006" -ForegroundColor White
Write-Host "  Orchestrator:    http://localhost:8007" -ForegroundColor White
Write-Host "  Sanctions API:   http://localhost:8004" -ForegroundColor White
Write-Host "  Geo Risk API:    http://localhost:8006" -ForegroundColor White
Write-Host "  ngrok Inspector: http://localhost:4040" -ForegroundColor White
Write-Host ""

# Get ngrok URLs
Write-Host "Fetching public ngrok URLs..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

try {
    $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 10
    Write-Host ""
    Write-Host "PUBLIC URLS (share these!):" -ForegroundColor Green
    foreach ($tunnel in $response.tunnels) {
        Write-Host "  $($tunnel.name): $($tunnel.public_url)" -ForegroundColor Cyan
    }
} catch {
    Write-Host "  Could not fetch ngrok URLs. Check http://localhost:4040 manually." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Commands:" -ForegroundColor Yellow
Write-Host "  .\START_DOCKER.ps1 -Status   # Check service status and URLs" -ForegroundColor Gray
Write-Host "  .\START_DOCKER.ps1 -Logs     # View logs" -ForegroundColor Gray
Write-Host "  .\START_DOCKER.ps1 -Down     # Stop all services" -ForegroundColor Gray
Write-Host "  .\START_DOCKER.ps1 -Build    # Rebuild and start" -ForegroundColor Gray
Write-Host ""
