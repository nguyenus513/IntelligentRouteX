@echo off
setlocal
cd /d "%~dp0"

echo [IRX] Starting full Control Tower runtime...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-irx-all.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [IRX] Startup failed with exit code %EXIT_CODE%.
  echo [IRX] Check .runtime\start-summary.json and .runtime\*.log for details.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo [IRX] Startup complete. Browser should be open at http://localhost:5173
pause
exit /b 0
