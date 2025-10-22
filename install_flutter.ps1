# Flutter Installation Script for Windows
Write-Host "Installing Flutter SDK for AMTTP Project..." -ForegroundColor Green

# Create Flutter directory
$flutterDir = "C:\flutter"
if (!(Test-Path $flutterDir)) {
    New-Item -ItemType Directory -Path $flutterDir
    Write-Host "Created Flutter directory at $flutterDir" -ForegroundColor Yellow
}

# Download Flutter (using a different approach)
Write-Host "Please follow these manual steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Open your browser and go to: https://docs.flutter.dev/get-started/install/windows" -ForegroundColor White
Write-Host "2. Download the Flutter SDK (stable channel)" -ForegroundColor White
Write-Host "3. Extract the zip file to C:\flutter" -ForegroundColor White
Write-Host "4. Add C:\flutter\bin to your PATH environment variable" -ForegroundColor White
Write-Host ""

# Alternative: Create a simple batch script to add to PATH
$batchScript = @"
@echo off
echo Adding Flutter to PATH...
setx PATH "%PATH%;C:\flutter\bin" /M
echo Flutter added to PATH. Please restart your PowerShell session.
pause
"@

$batchScript | Out-File -FilePath "C:\amttp\add_flutter_to_path.bat" -Encoding ASCII

Write-Host "Created batch script at C:\amttp\add_flutter_to_path.bat" -ForegroundColor Green
Write-Host "Run this script as Administrator after extracting Flutter to add it to PATH" -ForegroundColor Yellow
Write-Host ""

# For now, let's proceed with our Flutter project structure
Write-Host "Meanwhile, I've already created the complete Flutter project structure for you!" -ForegroundColor Green
Write-Host "Location: C:\amttp\frontend\amttp_app" -ForegroundColor Cyan
Write-Host ""
Write-Host "After installing Flutter, you can run:" -ForegroundColor White
Write-Host "  cd C:\amttp\frontend\amttp_app" -ForegroundColor Gray
Write-Host "  flutter pub get" -ForegroundColor Gray
Write-Host "  flutter run -d chrome" -ForegroundColor Gray