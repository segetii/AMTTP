@echo off
REM ================================================================
REM  FROZEN-NORMAL-WINDOW SIMULATION
REM  SIAM §7 no-lookahead protocol
REM  Datasets: FDIC | ERCOT | TerraLuna
REM
REM  HOW TO RUN (from any command prompt or PowerShell window):
REM    cd c:\amttp
REM    run_frozen_sim.bat
REM
REM  Output files written to:
REM    c:\amttp\research\adaptive-friction\frozen_normal_results.json
REM    c:\amttp\research\adaptive-friction\frozen_normal_timeline.txt
REM    c:\amttp\frozen_sim_log.txt   (full console log)
REM ================================================================

cd /d c:\amttp

echo.
echo Running frozen-normal-window simulation...
echo Output will appear here AND be saved to: c:\amttp\frozen_sim_log.txt
echo.

py -3 research\adaptive-friction\run_frozen_normal_simulation.py 2>&1 | powershell -Command "$input | Tee-Object -FilePath 'c:\amttp\frozen_sim_log.txt'"

echo.
echo ================================================================
echo Done.
echo Results JSON : c:\amttp\research\adaptive-friction\frozen_normal_results.json
echo Results text : c:\amttp\research\adaptive-friction\frozen_normal_timeline.txt
echo Full log     : c:\amttp\frozen_sim_log.txt
echo ================================================================
pause
