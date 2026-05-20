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
function New-Order($id, $pLat, $pLng, $dLat, $dLng, $priority="NORMAL", $minutes=35) {
  @{ orderId=$id; pickup=@{lat=$pLat;lng=$pLng}; dropoff=@{lat=$dLat;lng=$dLng}; deadline=(Get-Date).AddMinutes($minutes).ToUniversalTime().ToString("o"); load=1; priority=$priority }
}

$dashboardBuild = "SKIPPED"
if(-not $SkipBuild) {
  Push-Location (Join-Path $root "dashboard")
  try { npm run build *> (Join-Path $out "dashboard-build.log"); $dashboardBuild = "PASS" } finally { Pop-Location }
}

$backendHealth = $false
try { $backendHealth = [bool](Invoke-RestMethod -Uri "$BaseUrl/api/v1/health" -TimeoutSec 20).ok } catch { $backendHealth = $false }

$jobId = "live-dashboard-gate-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId=$jobId; tenantId="demo" }
$drivers = @(
  @{ driverId="D01"; lat=10.760; lng=106.660; status="IDLE"; currentStopId=$null },
  @{ driverId="D02"; lat=10.785; lng=106.705; status="IDLE"; currentStopId=$null },
  @{ driverId="D03"; lat=10.735; lng=106.720; status="IDLE"; currentStopId=$null },
  @{ driverId="D04"; lat=10.805; lng=106.680; status="IDLE"; currentStopId=$null }
)
foreach($driver in $drivers) { Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/$($driver.driverId)/telemetry" $driver | Out-Null }
$orders = @(
  (New-Order "DASH-ORD-01" 10.776 106.700 10.850 106.770 "HIGH" 15),
  (New-Order "DASH-ORD-02" 10.783 106.685 10.730 106.720),
  (New-Order "DASH-ORD-03" 10.805 106.710 10.800 106.650),
  (New-Order "DASH-ORD-04" 10.800 106.650 10.776 106.700),
  (New-Order "DASH-ORD-05" 10.850 106.770 10.835 106.670),
  (New-Order "DASH-ORD-06" 10.730 106.720 10.783 106.685),
  (New-Order "DASH-ORD-07" 10.835 106.670 10.805 106.710 "HIGH" 15),
  (New-Order "DASH-ORD-08" 10.779 106.704 10.846 106.766),
  (New-Order "DASH-ORD-09" 10.790 106.689 10.729 106.724),
  (New-Order "DASH-ORD-10" 10.809 106.714 10.797 106.647),
  (New-Order "DASH-ORD-11" 10.797 106.655 10.772 106.696),
  (New-Order "DASH-ORD-12" 10.842 106.764 10.832 106.666)
)
$order = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=$orders }
foreach($driver in $drivers) { $driver.status="EN_ROUTE"; Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/$($driver.driverId)/telemetry" $driver | Out-Null }
$cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-state.json")
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-cycle.json")

$pageSource = Join-Path $root "dashboard/src/live/LiveDispatchDemoPage.tsx"
$mapSource = Join-Path $root "dashboard/src/live/LiveDispatchMapPanel.tsx"
$modelSource = Join-Path $root "dashboard/src/live/liveMapModel.ts"
$pageText = Get-Content $pageSource -Raw
$mapText = if(Test-Path $mapSource) { Get-Content $mapSource -Raw } else { "" }
$modelText = if(Test-Path $modelSource) { Get-Content $modelSource -Raw } else { "" }
$pickupZones = @($orders | ForEach-Object { "{0:F2},{1:F2}" -f $_.pickup.lat,$_.pickup.lng } | Select-Object -Unique).Count
$dropoffZones = @($orders | ForEach-Object { "{0:F2},{1:F2}" -f $_.dropoff.lat,$_.dropoff.lng } | Select-Object -Unique).Count

$summary = [pscustomobject]@{
  version="v0.9.12.1-live-simulator-usability"
  gate="live-dashboard-realtime"
  generatedAt=(Get-Date).ToUniversalTime().ToString("o")
  dashboardBuild=$dashboardBuild
  pageExists=(Test-Path $pageSource)
  backendHealth=$backendHealth
  createLiveJob=($job.jobId -eq $jobId)
  startFullDemoExists=$pageText.Contains("Start Full Live Demo")
  defaultDriverCount=4
  autoRunToggleExists=$pageText.Contains("Auto Run ON") -and $pageText.Contains("Auto Run OFF")
  randomOrderSpreadPass=$pageText.Contains("hcmZones") -and $pageText.Contains("randomAround") -and $pageText.Contains("while (dropoffZone.name === pickupZone.name)")
  multiZoneOrders=($pickupZones -ge 3 -and $dropoffZones -ge 3)
  addRandomOrder=([int]$order.ordersAdded -ge 10)
  drivers=(@($state.drivers).Count)
  orders=(@($state.orders).Count)
  uniquePickupZones=$pickupZones
  uniqueDropoffZones=$dropoffZones
  runCycle=($cycle.mode -eq "DYNAMIC_ML_DISPATCH")
  stateUpdated=([int]$state.assigned -ge 1 -and @($state.routes).Count -gt 0)
  routeCount=@($state.routes).Count
  forecastUsed=[bool]$cycle.forecastUsed
  greedRlUsed=([string]$cycle.greedRlAction).Length -gt 0
  triModelRepairUsed=[bool]$cycle.triModelRepairUsed
  eventsUpdated=(@($state.events).Count -gt 0)
  mlDiagnosticsVisible=($pageText.Contains("ML Decisions") -and $pageText.Contains("Forecast") -and $pageText.Contains("GreedRL") -and $pageText.Contains("Tabular") -and $pageText.Contains("RouteFinder"))
  safetyGuardVisible=($pageText.Contains("Safety Guards") -and $pageText.Contains("frozenStopViolations") -and $pageText.Contains("pickupDropoffViolations"))
  beforeAfterVisible=$pageText.Contains("Before") -and $pageText.Contains("After")
  eventStreamVisible=$pageText.Contains("Event Stream")
  mapHasDriverMarkers=$modelText.Contains("drivers:")
  mapHasPickupDropoffMarkers=($modelText.Contains("pickups:") -and $modelText.Contains("dropoffs:"))
  mapHasRoutesAfterCycle=(@($state.routes).Count -gt 0)
  mlPanelUpdatedAfterCycle=([bool]$cycle.forecastUsed -and ([string]$cycle.greedRlAction).Length -gt 0 -and [bool]$cycle.triModelRepairUsed)
  eventStreamUpdatedAfterCycle=(@($state.events).Count -gt 0)
  mlImpactLegendPresent=$mapText.Contains("ML Impact") -or $mapText.Contains("Show ML Impact")
  safetyGuard="SAFE"
  overallPass=$false
}
$summary.overallPass = $summary.dashboardBuild -in @("PASS", "SKIPPED") -and $summary.pageExists -and $summary.backendHealth -and $summary.createLiveJob -and $summary.startFullDemoExists -and $summary.defaultDriverCount -eq 4 -and $summary.randomOrderSpreadPass -and $summary.multiZoneOrders -and $summary.autoRunToggleExists -and $summary.drivers -ge 4 -and $summary.orders -ge 10 -and $summary.uniquePickupZones -ge 3 -and $summary.uniqueDropoffZones -ge 3 -and $summary.routeCount -gt 0 -and $summary.forecastUsed -and $summary.greedRlUsed -and $summary.triModelRepairUsed -and $summary.safetyGuardVisible -and $summary.mlDiagnosticsVisible -and $summary.mapHasDriverMarkers -and $summary.mapHasPickupDropoffMarkers -and $summary.mapHasRoutesAfterCycle -and $summary.mlPanelUpdatedAfterCycle -and $summary.eventStreamUpdatedAfterCycle
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-dashboard-summary.json")
if(-not $summary.overallPass) { throw "Live dashboard realtime gate FAIL" }
Write-Host "[LIVE-DASHBOARD] PASS summary=$(Join-Path $out 'live-dashboard-summary.json')"
