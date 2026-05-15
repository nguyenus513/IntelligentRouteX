@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\start-system.ps1"
echo.
echo Full Dispatch V2 startup command finished. If a worker is missing, startup stops instead of falling back.
pause
