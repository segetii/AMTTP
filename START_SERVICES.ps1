# AMTTP Service Startup Script
# Last Updated: January 19, 2026
# Run this script to start all AMTTP services

param(
    [switch]$SkipDocker,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   AMTTP Service Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$BaseDir = "c:\amttp"

# Function to check if port is in use
function Test-Port {
    param([int]$Port)
    $result = netstat -ano | Select-String ":$Port.*LISTENING"
    return $null -ne $result
}

# Function to start a service
function Start-Service {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkDir,
        [int]$Port
    )
    
    if (Test-Port $Port) {
        Write-Host "[SKIP] $Name already running on port $Port" -ForegroundColor Yellow
        return
    }
    
    Write-Host "[START] $Name on port $Port..." -ForegroundColor Green
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", "cd '$WorkDir'; $Command" -WindowStyle Minimized
    Start-Sleep -Seconds 2
}

# Step 1: Docker Infrastructure
if (-not $SkipDocker -and -not $FrontendOnly) {
    Write-Host "`n[DOCKER] Starting infrastructure..." -ForegroundColor Magenta
    Set-Location $BaseDir
    docker-compose up -d
    Start-Sleep -Seconds 5
}

# Step 2: Backend Services
if (-not $FrontendOnly) {
    Write-Host "`n[BACKEND] Starting microservices..." -ForegroundColor Magenta
    
    # ML Risk API (8000)
    Start-Service -Name "ML Risk API" -Port 8000 `
        -Command "py -3 hybrid_api.py" `
        -WorkDir "$BaseDir\ml\Automation\ml_pipeline\inference"
    
    # Graph Service (8001)
    Start-Service -Name "Graph Service" -Port 8001 `
        -Command "py -3 run_graph_server.py" `
        -WorkDir "$BaseDir\ml\Automation\ml_pipeline\inference"
    
    # Policy Service (8003)
    Start-Service -Name "Policy Service" -Port 8003 `
        -Command "py -3 policy_api.py" `
        -WorkDir "$BaseDir\backend\policy-service"
    
    # Sanctions Service (8004)
    Start-Service -Name "Sanctions Service" -Port 8004 `
        -Command "py -3 sanctions_service.py" `
        -WorkDir "$BaseDir\backend\compliance-service"
    
    # Monitoring Engine (8005)
    Start-Service -Name "Monitoring Engine" -Port 8005 `
        -Command "py -3 monitoring_rules.py" `
        -WorkDir "$BaseDir\backend\compliance-service"
    
    # Geographic Risk (8006)
    Start-Service -Name "Geographic Risk" -Port 8006 `
        -Command "py -3 geographic_risk.py" `
        -WorkDir "$BaseDir\backend\compliance-service"
    
    # Orchestrator (8007)
    Start-Service -Name "Orchestrator" -Port 8007 `
        -Command "py -3 orchestrator.py" `
        -WorkDir "$BaseDir\backend\compliance-service"
    
    # Integrity Service (8008)
    Start-Service -Name "Integrity Service" -Port 8008 `
        -Command "py -3 integrity_service.py" `
        -WorkDir "$BaseDir\backend\compliance-service"
}

# Step 3: Frontend Services
if (-not $BackendOnly) {
    Write-Host "`n[FRONTEND] Starting web applications..." -ForegroundColor Magenta
    
    # Flutter Web (3010)
    Start-Service -Name "Flutter Web" -Port 3010 `
        -Command "py -3 flutter_server.py" `
        -WorkDir "$BaseDir\frontend\amttp_app"
    
    # Next.js Dashboard (3006)
    Start-Service -Name "Next.js Dashboard" -Port 3006 `
        -Command "npm run dev -- -p 3006" `
        -WorkDir "$BaseDir\frontend\frontend"
}

# Step 4: Verify
Write-Host "`n[VERIFY] Checking services..." -ForegroundColor Magenta
Start-Sleep -Seconds 5

$services = @(
    @{Name="ML Risk API"; Port=8000},
    @{Name="Graph Service"; Port=8001},
    @{Name="Policy Service"; Port=8003},
    @{Name="Sanctions Service"; Port=8004},
    @{Name="Monitoring Engine"; Port=8005},
    @{Name="Geographic Risk"; Port=8006},
    @{Name="Orchestrator"; Port=8007},
    @{Name="Integrity Service"; Port=8008},
    @{Name="Flutter Web"; Port=3010},
    @{Name="Next.js Dashboard"; Port=3006}
)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Service Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

foreach ($svc in $services) {
    if (Test-Port $svc.Port) {
        Write-Host "[OK] $($svc.Name) (port $($svc.Port))" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $($svc.Name) (port $($svc.Port))" -ForegroundColor Red
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   Access URLs" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Flutter App:      http://localhost:3010" -ForegroundColor White
Write-Host "Next.js Dashboard: http://localhost:3006" -ForegroundColor White
Write-Host "Orchestrator API: http://localhost:8007/health" -ForegroundColor White
Write-Host ""
