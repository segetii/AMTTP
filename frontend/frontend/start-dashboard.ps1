# Start AMTTP Next.js Dashboard
Set-Location "c:\amttp\frontend\frontend"
$env:PORT = "3004"
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  Starting AMTTP Next.js Dashboard..." -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Dashboard will be available at:" -ForegroundColor Yellow
Write-Host "  http://localhost:3004" -ForegroundColor Green
Write-Host ""
Write-Host "Features:" -ForegroundColor Yellow
Write-Host "  - Real-time SIEM Monitoring Dashboard" -ForegroundColor White
Write-Host "  - Live Security Alerts (auto-refresh every 30s)" -ForegroundColor White
Write-Host "  - Transaction Timeline Charts" -ForegroundColor White
Write-Host "  - Risk Distribution Analytics" -ForegroundColor White
Write-Host "  - UI Integrity Protection (on /transfer page)" -ForegroundColor White
Write-Host ""
Write-Host "DO NOT CLOSE THIS WINDOW" -ForegroundColor Red
Write-Host ""

npm run dev

Read-Host "Press Enter to exit"
