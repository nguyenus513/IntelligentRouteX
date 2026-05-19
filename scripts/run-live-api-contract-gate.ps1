param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-api-contract",
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

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="live-api-contract" }
$orders = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId="ORD-API-1"; pickup=@{lat=10.1; lng=106.1}; dropoff=@{lat=10.2; lng=106.2}; deadline="2026-05-20T10:30:00Z"; load=1; priority="HIGH" }) }
$telemetry = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.12; lng=106.12; status="EN_ROUTE"; currentStopId="PICKUP:ORD-API-1" }
$cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$rescue = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/rescue" @{}
$events = $state.events

$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="live-api-contract"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  createJobPass=($job.jobId -eq "live-api-contract")
  addOrderPass=([int]$orders.ordersAdded -eq 1)
  telemetryPass=($telemetry.status -eq "UPDATED")
  cyclePass=($cycle.mode -eq "DYNAMIC_ML_DISPATCH" -and [bool]$cycle.forecastUsed -and [bool]$cycle.triModelRepairUsed)
  statePass=($state.jobId -eq $job.jobId -and [int]$state.assigned -ge 1)
  rescuePass=($rescue.mode -eq "DYNAMIC_ML_DISPATCH")
  eventsEmitted=@($events).Count
  eventOrderValid=(@($events).Count -gt 0 -and @($events)[0].type -eq "ORDER_RECEIVED")
  missingCriticalEvents=0
  overallPass=$false
}
$critical = @("ORDER_RECEIVED", "DRIVER_TELEMETRY_UPDATED", "FORECAST_RISK_UPDATED", "GREEDRL_ACTION_SELECTED", "ROUTE_REOPTIMIZED", "DISPATCH_COMPLETED")
$types = @($events | ForEach-Object type)
$summary.missingCriticalEvents = @($critical | Where-Object { $types -notcontains $_ }).Count
$summary.overallPass = $summary.createJobPass -and $summary.addOrderPass -and $summary.telemetryPass -and $summary.cyclePass -and $summary.statePass -and $summary.rescuePass -and $summary.eventsEmitted -gt 0 -and $summary.eventOrderValid -and $summary.missingCriticalEvents -eq 0
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-api-contract-summary.json")
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-api-state.json")
if(-not $summary.overallPass) { throw "Live API contract gate FAIL" }
Write-Host "[LIVE-API] PASS summary=$(Join-Path $out 'live-api-contract-summary.json')"

