# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Docker Build & Run Script (Windows PowerShell)
# ═══════════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

$IMAGE_NAME = "amttp-platform"
$CONTAINER_NAME = "amttp-unified"

Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    AMTTP Platform - Docker Deployment                        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# Check if Docker is running
try {
    docker info | Out-Null
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🔨 Building Docker image... (this may take 5-10 minutes)" -ForegroundColor Yellow
docker build -t $IMAGE_NAME .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🧹 Stopping existing container if running..." -ForegroundColor Yellow
docker stop $CONTAINER_NAME 2>$null
docker rm $CONTAINER_NAME 2>$null

Write-Host ""
Write-Host "🚀 Starting AMTTP Platform..." -ForegroundColor Green
docker run -d `
    --name $CONTAINER_NAME `
    -p 80:80 `
    -p 3004:3004 `
    -p 8002:8002 `
    -p 8004:8004 `
    -p 8005:8005 `
    -p 8006:8006 `
    -p 8007:8007 `
    $IMAGE_NAME

Write-Host ""
Write-Host "⏳ Waiting for services to start (30 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Check health
try {
    $health = Invoke-RestMethod -Uri "http://localhost/health" -TimeoutSec 10 -ErrorAction SilentlyContinue
    
    Write-Host "✅ AMTTP Platform is running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║                              Access URLs                                      ║" -ForegroundColor Cyan
    Write-Host "╠══════════════════════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "║  🌐 Main App (Flutter):     http://localhost                                 ║" -ForegroundColor White
    Write-Host "║  📊 Dashboard (Next.js):    http://localhost:3004                            ║" -ForegroundColor White
    Write-Host "║  🔌 API (Orchestrator):     http://localhost:8007/docs                       ║" -ForegroundColor White
    Write-Host "║  🌍 Geo-Risk API:           http://localhost:8006/docs                       ║" -ForegroundColor White
    Write-Host "║  ❤️  Health Check:          http://localhost/health                          ║" -ForegroundColor White
    Write-Host "╚══════════════════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To view logs: docker logs -f $CONTAINER_NAME" -ForegroundColor Gray
    Write-Host "To stop:      docker stop $CONTAINER_NAME" -ForegroundColor Gray
    
    # Open in browser
    Start-Process "http://localhost"
    
} catch {
    Write-Host "⚠️  Platform started but health check failed. Check logs:" -ForegroundColor Yellow
    Write-Host "   docker logs $CONTAINER_NAME" -ForegroundColor Gray
}
