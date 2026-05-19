param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-event-stream",
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
function Post-Json($uri, $body) { Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec 120 }
function Get-Json($uri) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 120 }
if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="live-event-gate" }
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId="ORD-EVENT-1"; pickup=@{lat=10.1; lng=106.1}; dropoff=@{lat=10.2; lng=106.2}; deadline="2026-05-20T10:30:00Z"; load=1; priority="HIGH" }) } | Out-Null
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.12; lng=106.12; status="EN_ROUTE"; currentStopId="PICKUP:ORD-EVENT-1" } | Out-Null
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true } | Out-Null
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$sse = & curl.exe --max-time 5 -s "$BaseUrl/api/v1/live/jobs/$($job.jobId)/events"
$sse | Set-Content -Encoding UTF8 (Join-Path $out "live-events.sse")
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-event-state.json")

$critical = @("ORDER_RECEIVED", "ORDER_BUFFERED", "DRIVER_TELEMETRY_UPDATED", "FORECAST_RISK_UPDATED", "GREEDRL_ACTION_SELECTED", "ROUTE_REOPTIMIZED", "DISPATCH_COMPLETED")
$types = @($state.events | ForEach-Object type)
$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="live-event-stream"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  eventsEmitted=@($state.events).Count
  sseEventLines=@($sse | Where-Object { $_ -like "event:*" }).Count
  eventOrderValid=($types.Count -gt 0 -and $types[0] -eq "ORDER_RECEIVED")
  missingCriticalEvents=@($critical | Where-Object { $types -notcontains $_ }).Count
  dashboardCanReadEvents=($sse -join "`n").Contains("event:FORECAST_RISK_UPDATED")
  overallPass=$false
}
$summary.overallPass = $summary.eventsEmitted -gt 0 -and $summary.sseEventLines -gt 0 -and $summary.eventOrderValid -and $summary.missingCriticalEvents -eq 0 -and $summary.dashboardCanReadEvents
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-event-stream-summary.json")
if(-not $summary.overallPass) { throw "Live event stream gate FAIL" }
Write-Host "[LIVE-EVENTS] PASS summary=$(Join-Path $out 'live-event-stream-summary.json')"
