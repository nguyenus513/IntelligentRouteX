param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.12-live-dashboard/live-dashboard",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
function Post-Json($uri, $body) { Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec 120 }
function Get-Json($uri) { Invoke-RestMethod -Method Get -Uri $uri -Headers $headers -TimeoutSec 120 }

$dashboardBuild = "SKIPPED"
if(-not $SkipBuild) {
  Push-Location (Join-Path $root "dashboard")
  try { npm run build *> (Join-Path $out "dashboard-build.log"); $dashboardBuild = "PASS" } finally { Pop-Location }
}

$backendHealth = $false
try { $backendHealth = [bool](Invoke-RestMethod -Uri "$BaseUrl/api/v1/health" -TimeoutSec 20).ok } catch { $backendHealth = $false }

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="live-dashboard-gate"; tenantId="demo" }
$order = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId="DASH-ORD-1"; pickup=@{lat=10.75;lng=106.70}; dropoff=@{lat=10.82;lng=106.78}; deadline="2026-05-20T10:30:00Z"; load=1; priority="HIGH" }) }
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.76; lng=106.71; status="EN_ROUTE"; currentStopId="PICKUP:DASH-ORD-1" } | Out-Null
$cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-state.json")
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-cycle.json")

$pageSource = Join-Path $root "dashboard/src/live/LiveDispatchDemoPage.tsx"
$pageText = Get-Content $pageSource -Raw
$summary = [pscustomobject]@{
  version="v0.9.12-live-dashboard-demo"
  gate="live-dashboard-realtime"
  generatedAt=(Get-Date).ToUniversalTime().ToString("o")
  dashboardBuild=$dashboardBuild
  pageExists=(Test-Path $pageSource)
  backendHealth=$backendHealth
  createLiveJob=($job.jobId -eq "live-dashboard-gate")
  addRandomOrder=([int]$order.ordersAdded -eq 1)
  runCycle=($cycle.mode -eq "DYNAMIC_ML_DISPATCH")
  stateUpdated=([int]$state.assigned -ge 1 -and @($state.routes).Count -gt 0)
  eventsUpdated=(@($state.events).Count -gt 0)
  mlDiagnosticsVisible=($pageText.Contains("ML Decisions") -and $pageText.Contains("Forecast") -and $pageText.Contains("GreedRL") -and $pageText.Contains("Tabular") -and $pageText.Contains("RouteFinder"))
  safetyGuardVisible=($pageText.Contains("Safety Guards") -and $pageText.Contains("frozenStopViolations") -and $pageText.Contains("pickupDropoffViolations"))
  beforeAfterVisible=$pageText.Contains("Before") -and $pageText.Contains("After")
  eventStreamVisible=$pageText.Contains("Event Stream")
  overallPass=$false
}
$summary.overallPass = $summary.dashboardBuild -in @("PASS", "SKIPPED") -and $summary.pageExists -and $summary.backendHealth -and $summary.createLiveJob -and $summary.addRandomOrder -and $summary.runCycle -and $summary.stateUpdated -and $summary.eventsUpdated -and $summary.mlDiagnosticsVisible -and $summary.safetyGuardVisible -and $summary.beforeAfterVisible -and $summary.eventStreamVisible
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-summary.json")
if(-not $summary.overallPass) { throw "Live dashboard realtime gate FAIL" }
Write-Host "[LIVE-DASHBOARD] PASS summary=$(Join-Path $out 'live-dashboard-summary.json')"
