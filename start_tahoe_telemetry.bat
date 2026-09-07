@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "Tahoe Telemetry" ".venv\Scripts\pythonw.exe" -m tahoe_telemetry
    exit /b 0
)

where python3.11 >nul 2>nul
if %errorlevel% equ 0 (
    start "Tahoe Telemetry" python3.11 -m tahoe_telemetry
    exit /b 0
)

py -3.11 -c "import sys" >nul 2>nul
if %errorlevel% equ 0 (
    start "Tahoe Telemetry" py -3.11 -m tahoe_telemetry
    exit /b 0
)

echo Python 3.11 was not found. Install 64-bit Python 3.11 and run setup again.
pause
exit /b 1

