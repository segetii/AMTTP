# =============================================================================
# AMTTP Full Stack Launcher with Public Web Exposure
# =============================================================================
# This script starts:
#   1. Flutter Consumer App (port 8889)
#   2. Next.js War Room (port 3006)
#   3. Nginx Gateway + ngrok (exposes everything to the web)
# =============================================================================

param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║           AMTTP Full Stack Public Web Launcher                     ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Stop command
if ($Stop) {
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    docker-compose -f docker-compose.gateway.yml down 2>$null
    Stop-Process -Name node -Force -ErrorAction SilentlyContinue
    Stop-Process -Name ngrok -Force -ErrorAction SilentlyContinue
    Write-Host "All services stopped." -ForegroundColor Green
    exit 0
}

# Status command
if ($Status) {
    Write-Host "Service Status:" -ForegroundColor Yellow
    Write-Host ""
    
    # Check Flutter
    $flutter = netstat -ano 2>$null | Select-String ":8889.*LISTENING"
    if ($flutter) {
        Write-Host "  ✓ Flutter App (8889): Running" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Flutter App (8889): Not running" -ForegroundColor Red
    }
    
    # Check Next.js
    $nextjs = netstat -ano 2>$null | Select-String ":3006.*LISTENING"
    if ($nextjs) {
        Write-Host "  ✓ Next.js War Room (3006): Running" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Next.js War Room (3006): Not running" -ForegroundColor Red
    }
    
    # Check Gateway
    $gateway = netstat -ano 2>$null | Select-String ":8080.*LISTENING"
    if ($gateway) {
        Write-Host "  ✓ Gateway (8080): Running" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Gateway (8080): Not running" -ForegroundColor Red
    }
    
    # Check Orchestrator
    $orch = netstat -ano 2>$null | Select-String ":8007.*LISTENING"
    if ($orch) {
        Write-Host "  ✓ Orchestrator (8007): Running" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Orchestrator (8007): Not running" -ForegroundColor Red
    }
    
    Write-Host ""
    
    # Get ngrok URL
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.tunnels.Count -gt 0) {
            Write-Host "PUBLIC URL:" -ForegroundColor Green
            foreach ($tunnel in $response.tunnels) {
                Write-Host "  $($tunnel.public_url)" -ForegroundColor Cyan
            }
        }
    } catch {
        Write-Host "  ngrok not running or URL not available" -ForegroundColor Yellow
    }
    
    exit 0
}

# =============================================================================
# Start Services
# =============================================================================

Write-Host "Step 1: Checking prerequisites..." -ForegroundColor Yellow

# Check Docker
try {
    docker info 2>$null | Out-Null
    Write-Host "  ✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# =============================================================================
# Step 2: Start Flutter App
# =============================================================================
Write-Host ""
Write-Host "Step 2: Starting Flutter Consumer App..." -ForegroundColor Yellow

$flutterRunning = netstat -ano 2>$null | Select-String ":8889.*LISTENING"
if (-not $flutterRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\amttp\frontend\amttp_app\build\web; Write-Host 'Flutter App starting on port 8889...' -ForegroundColor Cyan; npx serve -s -l 8889" -WindowStyle Minimized
    Start-Sleep -Seconds 3
}
Write-Host "  ✓ Flutter App: http://localhost:8889" -ForegroundColor Green

# =============================================================================
# Step 3: Start Next.js War Room
# =============================================================================
Write-Host ""
Write-Host "Step 3: Starting Next.js War Room..." -ForegroundColor Yellow

$nextjsRunning = netstat -ano 2>$null | Select-String ":3006.*LISTENING"
if (-not $nextjsRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\amttp\frontend\frontend; Write-Host 'Next.js War Room starting on port 3006...' -ForegroundColor Cyan; npx next dev -p 3006" -WindowStyle Minimized
    Start-Sleep -Seconds 10
}
Write-Host "  ✓ War Room: http://localhost:3006" -ForegroundColor Green

# =============================================================================
# Step 4: Start Gateway + ngrok
# =============================================================================
Write-Host ""
Write-Host "Step 4: Starting Gateway + ngrok..." -ForegroundColor Yellow

docker-compose -f docker-compose.gateway.yml up -d

Write-Host "  ✓ Gateway: http://localhost:8080" -ForegroundColor Green

# =============================================================================
# Step 5: Get Public URL
# =============================================================================
Write-Host ""
Write-Host "Step 5: Getting public URL..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

try {
    $response = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 10
    $publicUrl = $response.tunnels[0].public_url
    
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║                    🌐 AMTTP IS NOW LIVE!                          ║" -ForegroundColor Green
    Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "PUBLIC URL (share this!):" -ForegroundColor White
    Write-Host "  $publicUrl" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "ROUTES:" -ForegroundColor White
    Write-Host "  $publicUrl/              → Flutter Consumer App" -ForegroundColor Gray
    Write-Host "  $publicUrl/warroom/      → Next.js War Room" -ForegroundColor Gray
    Write-Host "  $publicUrl/api/          → Orchestrator API" -ForegroundColor Gray
    Write-Host ""
    Write-Host "LOCAL URLS:" -ForegroundColor White
    Write-Host "  http://localhost:8889    → Flutter App (direct)" -ForegroundColor Gray
    Write-Host "  http://localhost:3006    → War Room (direct)" -ForegroundColor Gray
    Write-Host "  http://localhost:8080    → Gateway" -ForegroundColor Gray
    Write-Host "  http://localhost:4040    → ngrok Inspector" -ForegroundColor Gray
    Write-Host ""
    Write-Host "COMMANDS:" -ForegroundColor Yellow
    Write-Host "  .\EXPOSE_WEB.ps1 -Status  → Check status" -ForegroundColor Gray
    Write-Host "  .\EXPOSE_WEB.ps1 -Stop    → Stop all services" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "  Could not get ngrok URL. Check http://localhost:4040" -ForegroundColor Yellow
}
