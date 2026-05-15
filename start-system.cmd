@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\start-system.ps1"
echo.
echo IntelligentRouteX startup command finished. Backend uses dispatch-v2-full-adaptive profile; TomTom OFF; frontend/backend stay open in separate windows.
pause

