param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-state-engine",
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
function Post-Json($uri, $body) { Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec 120 }
function Get-Json($uri) { Invoke-RestMethod -Method Get -Uri $uri -Headers $headers -TimeoutSec 120 }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="live-state-gate" }
$newOrdersInjected = 0
$driverTelemetryUpdates = 0
$cycles = @()
for($i=1; $i -le 4; $i++) {
  $orderId = "ORD-LIVE-$i"
  Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId=$orderId; pickup=@{lat=10.7 + ($i/1000); lng=106.6}; dropoff=@{lat=10.8; lng=106.7 + ($i/1000)}; deadline="2026-05-20T10:30:00Z"; load=1; priority=if($i % 2 -eq 0){"HIGH"}else{"NORMAL"} }) } | Out-Null
  $newOrdersInjected++
  Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.72 + ($i/1000); lng=106.62; status="EN_ROUTE"; currentStopId=if($i -gt 1){"PICKUP:ORD-LIVE-1"}else{$null} } | Out-Null
  $driverTelemetryUpdates++
  $cycles += Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
}
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-state.json")

$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="live-state-engine"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  stateCycles=$cycles.Count
  newOrdersInjected=$newOrdersInjected
  driverTelemetryUpdates=$driverTelemetryUpdates
  assigned=$state.assigned
  buffered=$state.buffered
  frozenStopCount=@($state.frozenStopIds).Count
  frozenStopViolations=(@($cycles | ForEach-Object { [int]$_.diagnostics.frozenStopViolations }) | Measure-Object -Sum).Sum
  missingOrderViolations=if($state.assigned + $state.buffered -lt $newOrdersInjected){1}else{0}
  overallPass=$false
}
$summary.overallPass = $summary.stateCycles -ge 4 -and $summary.newOrdersInjected -gt 0 -and $summary.driverTelemetryUpdates -gt 0 -and $summary.frozenStopViolations -eq 0 -and $summary.missingOrderViolations -eq 0
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-state-engine-summary.json")
if(-not $summary.overallPass) { throw "Live state engine gate FAIL" }
Write-Host "[LIVE-STATE] PASS summary=$(Join-Path $out 'live-state-engine-summary.json')"

