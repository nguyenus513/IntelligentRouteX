$ErrorActionPreference = "Stop"
$status = (curl.exe -s -o NUL -w "%{http_code}" http://localhost:3000/health)
if ($status -ne "200") {
  Write-Error "VROOM healthcheck failed with HTTP $status"
  exit 1
}
Write-Host "VROOM healthcheck OK"
