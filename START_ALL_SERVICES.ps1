# AMTTP Complete System Startup Script
# Launches all backend services and frontend applications in correct order
# Last Updated: January 8, 2026

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  AMTTP System Startup - Complete Stack Initialization" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$BACKEND_DIR = "c:\amttp\backend\compliance-service"
$POLICY_DIR = "c:\amttp\backend\policy-service"
$FLUTTER_DIR = "c:\amttp\frontend\amttp_app"
$NEXTJS_DIR = "c:\amttp\frontend\frontend"

# Port Configuration
$ports = @{
    "Memgraph" = 3000
    "Flutter" = 3003
    "NextJS" = 3004
    "PolicyService" = 8003
    "SanctionsService" = 8004
    "MonitoringService" = 8005
    "GeoRiskService" = 8006
    "Orchestrator" = 8007
    "IntegrityService" = 8008
}

# Function to check if port is in use
function Test-Port {
    param([int]$Port)
    $result = netstat -ano | findstr ":$Port.*LISTENING"
    return $result -ne $null
}

# Function to start service in new window
function Start-Service {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDir,
        [int]$Port
    )
    
    Write-Host "[$Name] Starting on port $Port..." -ForegroundColor Yellow
    
    if (Test-Port -Port $Port) {
        Write-Host "[$Name] [WARN] Port $Port already in use - skipping" -ForegroundColor DarkYellow
        return $false
    }
    
    $scriptBlock = @"
Write-Host '[$Name] Service Starting...' -ForegroundColor Green
Set-Location '$WorkingDir'
$Command
"@
    
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $scriptBlock
    Start-Sleep -Seconds 3
    
    if (Test-Port -Port $Port) {
        Write-Host "[$Name] [OK] Running on port $Port" -ForegroundColor Green
        return $true
    } else {
        Write-Host "[$Name] [ERROR] Failed to start" -ForegroundColor Red
        return $false
    }
}

Write-Host ""
Write-Host "Pre-Startup Check..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found - install Python 3.11+" -ForegroundColor Red
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version
    Write-Host "[OK] Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Node.js not found - install Node.js 18+" -ForegroundColor Red
    exit 1
}

# Check Flutter
try {
    $flutterVersion = flutter --version 2>&1 | Select-String "Flutter" | Select-Object -First 1
    Write-Host "[OK] Flutter: $flutterVersion" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Flutter not found - Flutter app won't start" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Starting Backend Services..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Track successful starts
$successCount = 0
$totalServices = 6

# 1. Policy Service (Port 8003)
if (Start-Service -Name "Policy Service" `
                  -Command "python policy_api.py" `
                  -WorkingDir $POLICY_DIR `
                  -Port $ports.PolicyService) {
    $successCount++
}

# 2. Sanctions Service (Port 8004)
if (Start-Service -Name "Sanctions Service" `
                  -Command "python sanctions_service.py" `
                  -WorkingDir $BACKEND_DIR `
                  -Port $ports.SanctionsService) {
    $successCount++
}

# 3. Monitoring Service (Port 8005)
if (Start-Service -Name "Monitoring Service" `
                  -Command "python monitoring_rules.py" `
                  -WorkingDir $BACKEND_DIR `
                  -Port $ports.MonitoringService) {
    $successCount++
}

# 4. Geographic Risk Service (Port 8006)
if (Start-Service -Name "Geographic Risk" `
                  -Command "python geographic_risk.py" `
                  -WorkingDir $BACKEND_DIR `
                  -Port $ports.GeoRiskService) {
    $successCount++
}

# 5. Orchestrator (Port 8007) - Start AFTER dependent services
Write-Host "[WAIT] Waiting 5 seconds for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

if (Start-Service -Name "Orchestrator" `
                  -Command "python orchestrator.py" `
                  -WorkingDir $BACKEND_DIR `
                  -Port $ports.Orchestrator) {
    $successCount++
}

# 6. UI Integrity Service (Port 8008) - Optional
if (Start-Service -Name "UI Integrity" `
                  -Command "python integrity_service.py" `
                  -WorkingDir $BACKEND_DIR `
                  -Port $ports.IntegrityService) {
    $successCount++
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Backend Services Summary" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Started: $successCount / $totalServices services" -ForegroundColor $(if ($successCount -eq $totalServices) { "Green" } else { "Yellow" })
Write-Host ""

if ($successCount -lt $totalServices) {
    Write-Host "[WARN] Some services failed to start. Check error messages above." -ForegroundColor DarkYellow
    Write-Host "       The system will work with reduced functionality." -ForegroundColor DarkYellow
    Write-Host ""
}

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Starting Frontend Applications..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Wait for backends to stabilize
Write-Host "[WAIT] Waiting 10 seconds for backend initialization..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 1. Flutter App (Port 3003)
Write-Host "[Flutter App] Starting on port $($ports.Flutter)..." -ForegroundColor Yellow

if (Test-Port -Port $ports.Flutter) {
    Write-Host "[Flutter App] [WARN] Port $($ports.Flutter) already in use - skipping" -ForegroundColor DarkYellow
} else {
    $flutterScript = @"
Write-Host '[Flutter App] Starting...' -ForegroundColor Green
Set-Location '$FLUTTER_DIR'
flutter run -d chrome --web-port=$($ports.Flutter)
"@
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $flutterScript
    Start-Sleep -Seconds 5
    Write-Host "[Flutter App] [OK] Started (will open browser when ready)" -ForegroundColor Green
}

# 2. Next.js Dashboard (Port 3004)
Write-Host "[Next.js Dashboard] Starting on port $($ports.NextJS)..." -ForegroundColor Yellow

if (Test-Port -Port $ports.NextJS) {
    Write-Host "[Next.js Dashboard] [WARN] Port $($ports.NextJS) already in use - skipping" -ForegroundColor DarkYellow
} else {
    $nextjsScript = @"
Write-Host '[Next.js Dashboard] Starting...' -ForegroundColor Green
Set-Location '$NEXTJS_DIR'
`$env:PORT=$($ports.NextJS)
npm run dev
"@
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $nextjsScript
    Start-Sleep -Seconds 5
    Write-Host "[Next.js Dashboard] [OK] Started (compiling...)" -ForegroundColor Green
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  AMTTP System Startup Complete!" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Frontend Applications:" -ForegroundColor Cyan
Write-Host "   Flutter App:       http://localhost:$($ports.Flutter)" -ForegroundColor White
Write-Host "   Next.js Dashboard: http://localhost:$($ports.NextJS)" -ForegroundColor White
Write-Host ""

Write-Host "Backend Services:" -ForegroundColor Cyan
Write-Host "   Policy Service:    http://localhost:$($ports.PolicyService)/health" -ForegroundColor White
Write-Host "   Sanctions:         http://localhost:$($ports.SanctionsService)/health" -ForegroundColor White
Write-Host "   Monitoring:        http://localhost:$($ports.MonitoringService)/health" -ForegroundColor White
Write-Host "   Geographic Risk:   http://localhost:$($ports.GeoRiskService)/health" -ForegroundColor White
Write-Host "   Orchestrator:      http://localhost:$($ports.Orchestrator)/health" -ForegroundColor White
Write-Host "   UI Integrity:      http://localhost:$($ports.IntegrityService)/health" -ForegroundColor White
Write-Host ""

Write-Host "Key Features:" -ForegroundColor Cyan
Write-Host "   • FATF Compliance:  http://localhost:$($ports.NextJS)/compliance" -ForegroundColor White
Write-Host "   • ML Dashboard:     http://localhost:$($ports.Flutter) (sign in as admin)" -ForegroundColor White
Write-Host "   • SIEM Monitoring:  http://localhost:$($ports.NextJS)/" -ForegroundColor White
Write-Host "   • Secure Transfer:  http://localhost:$($ports.NextJS)/transfer" -ForegroundColor White
Write-Host ""

Write-Host "Demo Credentials:" -ForegroundColor Cyan
Write-Host "   Next.js: admin@amttp.com / admin123" -ForegroundColor White
Write-Host "   Flutter: admin / admin123" -ForegroundColor White
Write-Host ""

Write-Host "Tip: Keep this window open to see startup summary" -ForegroundColor Yellow
Write-Host "    Each service runs in its own PowerShell window" -ForegroundColor Yellow
Write-Host ""

# Optional: Open browsers automatically
$openBrowsers = Read-Host "Open applications in browser? (Y/N)"
if ($openBrowsers -eq "Y" -or $openBrowsers -eq "y") {
    Write-Host ""
    Write-Host "🌐 Opening browsers..." -ForegroundColor Cyan
    Start-Sleep -Seconds 15  # Wait for compilation
    
    Start-Process "http://localhost:$($ports.NextJS)/compliance"
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:$($ports.Flutter)"
    
    Write-Host "✅ Browsers opened" -ForegroundColor Green
}

Write-Host ""
Write-Host "Press any key to exit this window (services will keep running)..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
