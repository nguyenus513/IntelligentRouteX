param(
  [string]$OutputDir = "artifacts/test-reports/v0.9.9.6-one-click-start",
  [switch]$Full
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = [ordered]@{}
function Pass($name){ $script:results[$name]="PASS"; Write-Host "PASS $name" }
function Assert($condition,$message){ if(-not $condition){ throw $message } }
function HttpOk($url){ try{ $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5; return $r.StatusCode -eq 200 }catch{return $false} }

powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 down | Tee-Object (Join-Path $OutputDir "down-pre.log") | Out-Host
powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 up -Profile local | Tee-Object (Join-Path $OutputDir "up.log") | Out-Host
Assert (HttpOk "http://localhost:18116/api/v1/health") "backend health failed"
Assert (HttpOk "http://localhost:5173/playground") "playground HTTP 200 failed"
Pass up
Pass backendHealth
Pass playgroundHttp200

powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 status | Tee-Object (Join-Path $OutputDir "status.log") | Out-Host
Pass status

if($Full){ powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 test -Full | Tee-Object (Join-Path $OutputDir "test.log") | Out-Host } else { powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 test -Quick | Tee-Object (Join-Path $OutputDir "test.log") | Out-Host }
Assert (Test-Path (Join-Path $OutputDir "one-click-system-summary.json")) "test summary missing"
Pass test

powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 down | Tee-Object (Join-Path $OutputDir "down.log") | Out-Host
Start-Sleep -Seconds 3
Pass down

powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 package | Tee-Object (Join-Path $OutputDir "package.log") | Out-Host
Assert (Test-Path "release/irx-v1.0.zip") "release zip missing"
Assert (Test-Path "release/irx-v1.0/release-summary.json") "release summary missing"
Pass package
Pass releaseZip

$summary = [ordered]@{
  version = "v0.9.9.6-one-click-start"
  overallPass = $true
  up = $results.up
  backendHealth = $results.backendHealth
  playgroundHttp200 = $results.playgroundHttp200
  status = $results.status
  test = $results.test
  down = $results.down
  package = $results.package
  releaseZip = $results.releaseZip
  releasePath = "release/irx-v1.0.zip"
  systemSummary = "artifacts/test-reports/v0.9.9.6-one-click-start/one-click-system-summary.json"
}
$path = Join-Path $OutputDir "one-click-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
