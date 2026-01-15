@echo off
REM AMTTP Compliance Services Startup Script
REM Starts all compliance microservices

echo ========================================
echo    AMTTP Compliance Services
echo ========================================
echo.

REM Set Python path
set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe

REM Create data directories
if not exist "data\sanctions" mkdir data\sanctions
if not exist "data\monitoring" mkdir data\monitoring
if not exist "data\geo" mkdir data\geo
if not exist "data\orchestrator" mkdir data\orchestrator

echo Starting Sanctions Screening Service (port 8004)...
start "Sanctions Service" cmd /c "%PYTHON% sanctions_service.py"
timeout /t 2 /nobreak > nul

echo Starting Transaction Monitoring Engine (port 8005)...
start "Monitoring Engine" cmd /c "%PYTHON% monitoring_rules.py"
timeout /t 2 /nobreak > nul

echo Starting Geographic Risk Service (port 8006)...
start "Geo Risk Service" cmd /c "%PYTHON% geographic_risk.py"
timeout /t 2 /nobreak > nul

echo Starting Compliance Orchestrator (port 8007)...
start "Orchestrator" cmd /c "%PYTHON% orchestrator.py"
timeout /t 2 /nobreak > nul

echo.
echo ========================================
echo    All services started!
echo ========================================
echo.
echo Sanctions Service:   http://localhost:8004
echo Monitoring Engine:   http://localhost:8005
echo Geographic Risk:     http://localhost:8006
echo.
echo Press any key to exit...
pause > nul
