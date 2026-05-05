@echo off
curl.exe -s -o NUL -w "%%{http_code}" http://localhost:3000/health | findstr /x "200" >NUL
if errorlevel 1 (
  echo VROOM healthcheck failed. Expected HTTP 200 from http://localhost:3000/health.
  exit /b 1
)
echo VROOM healthcheck OK
