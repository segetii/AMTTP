# Launch AMTTP Flutter App
Set-Location "c:\amttp\frontend\amttp_app"
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  Starting AMTTP Flutter App on Chrome..." -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Building app (this may take 60-90 seconds)..." -ForegroundColor Yellow
Write-Host "App will open automatically in Chrome when ready." -ForegroundColor Yellow
Write-Host ""
Write-Host "DO NOT CLOSE THIS WINDOW - Flutter is compiling..." -ForegroundColor Red
Write-Host ""

flutter run -d chrome --web-port=3003 --release

Read-Host "Press Enter to exit"
