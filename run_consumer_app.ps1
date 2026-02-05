# Run Flutter Consumer App
# This script builds and serves the streamlined consumer Flutter app

Write-Host "Building Flutter Consumer App..." -ForegroundColor Cyan
Set-Location "C:\amttp\frontend\amttp_app"

# Build for web
flutter build web -t lib/main_consumer.dart --no-tree-shake-icons

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful! Starting server..." -ForegroundColor Green
    
    # Serve the built app
    Set-Location "build\web"
    Write-Host "`nConsumer App available at: http://localhost:8889" -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Gray
    
    npx serve -s -l 8889
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
}
