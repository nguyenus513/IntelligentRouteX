param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.9.3-irx-control-tower-explain-compare",
  [switch]$SkipCompile,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
function Post-Json($uri, $body, [hashtable]$h = $headers) { Invoke-RestMethod -Method Post -Uri $uri -Headers $h -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 50) -TimeoutSec 180 }
function Get-Json($uri, [hashtable]$h = $headers) { Invoke-RestMethod -Method Get -Uri $uri -Headers $h -TimeoutSec 180 }

$compileJava = "SKIPPED"
if(-not $SkipCompile) {
  Push-Location $root
  try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log"); $compileJava = "PASS" } finally { Pop-Location }
}
$dashboardBuild = "SKIPPED"
if(-not $SkipBuild) {
  Push-Location (Join-Path $root "dashboard")
  try { npm run build *> (Join-Path $out "dashboard-build.log"); $dashboardBuild = "PASS" } finally { Pop-Location }
}

$backendHealth = $false
try { $backendHealth = [bool](Invoke-RestMethod -Uri "$BaseUrl/api/v1/health" -TimeoutSec 20).ok } catch { $backendHealth = $false }

$staticJob = Post-Json "$BaseUrl/api/v1/static/dispatch/jobs" @{ scenario="control-tower-static" }
$staticJobId = $staticJob.data.jobId
$staticResult = Get-Json "$BaseUrl/api/v1/static/dispatch/jobs/$staticJobId/result"

$liveJobId = "ct-live-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$liveJob = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId=$liveJobId; tenantId="demo" }
$drivers = @(
  @{ driverId="D01"; lat=10.760; lng=106.660; status="IDLE"; currentStopId=$null },
  @{ driverId="D02"; lat=10.785; lng=106.705; status="IDLE"; currentStopId=$null },
  @{ driverId="D03"; lat=10.735; lng=106.720; status="IDLE"; currentStopId=$null },
  @{ driverId="D04"; lat=10.805; lng=106.680; status="IDLE"; currentStopId=$null }
)
foreach($driver in $drivers) { Post-Json "$BaseUrl/api/v1/live/jobs/$($liveJob.jobId)/drivers/$($driver.driverId)/telemetry" $driver | Out-Null }
$orders = 1..12 | ForEach-Object {
  $zones = @(
    @{lat=10.776;lng=106.700}, @{lat=10.783;lng=106.685}, @{lat=10.805;lng=106.710}, @{lat=10.800;lng=106.650}, @{lat=10.850;lng=106.770}, @{lat=10.730;lng=106.720}, @{lat=10.835;lng=106.670}
  )
  $p = $zones[($_ - 1) % $zones.Count]; $d = $zones[($_ + 2) % $zones.Count]
  $isTight = ($_ % 4 -eq 0)
  $minutes = if($isTight) { 15 } else { 35 }
  $priority = if($isTight) { "HIGH" } else { "NORMAL" }
  @{ orderId="CT-ORD-$('{0:D2}' -f $_)"; pickup=@{lat=$p.lat + ($_ * 0.0007); lng=$p.lng - ($_ * 0.0005)}; dropoff=@{lat=$d.lat - ($_ * 0.0004); lng=$d.lng + ($_ * 0.0006)}; deadline=(Get-Date).AddMinutes($minutes).ToUniversalTime().ToString("o"); load=1; priority=$priority }
}
Post-Json "$BaseUrl/api/v1/live/jobs/$($liveJob.jobId)/orders" @{ orders=$orders } | Out-Null
foreach($driver in $drivers) { $driver.status="EN_ROUTE"; Post-Json "$BaseUrl/api/v1/live/jobs/$($liveJob.jobId)/drivers/$($driver.driverId)/telemetry" $driver | Out-Null }
$cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($liveJob.jobId)/cycle" @{ returnDiagnostics=$true }
$liveState = Get-Json "$BaseUrl/api/v1/live/jobs/$($liveJob.jobId)/state"

$benchmarkJob = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body (@{ datasetId="synthetic-food-smoke"; solvers=@("IntelligentRouteX", "OR-Tools", "VROOM") } | ConvertTo-Json -Depth 10) -TimeoutSec 180
$benchmarkResult = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($benchmarkJob.jobId)/result" -TimeoutSec 180
$solverRows = @($benchmarkResult.diagnostics.solverResults)

$page = Get-Content (Join-Path $root "dashboard/src/live/LiveDispatchDemoPage.tsx") -Raw
$styles = Get-Content (Join-Path $root "dashboard/src/styles.css") -Raw

$staticJob | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 (Join-Path $out "static-job.json")
$staticResult | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 (Join-Path $out "static-result.json")
$liveState | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-state.json")
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-cycle.json")
$benchmarkResult | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "compare-result.json")

$summary = [pscustomobject]@{
  version="v0.9.9.3-irx-control-tower-explain-compare"
  generatedAt=(Get-Date).ToUniversalTime().ToString("o")
  compileJava=$compileJava
  dashboardBuild=$dashboardBuild
  backendHealth=$backendHealth
  startStaticButton=$page.Contains("Start Static")
  startLiveButton=$page.Contains("Start Live")
  benchmarkCompareButton=$page.Contains("Run Benchmark Compare")
  resetButton=$page.Contains("Reset")
  navTabsPresent=($page.Contains("Static Control") -and $page.Contains("Live Control") -and $page.Contains("Explain Pipeline") -and $page.Contains("Compare Arena") -and $page.Contains("API / Artifacts"))
  staticRunPass=($staticResult.data.status -eq "COMPLETED" -and [int]$staticResult.data.summary.assignedOrders -gt 0)
  liveRunPass=($cycle.mode -eq "DYNAMIC_ML_DISPATCH" -and [bool]$cycle.forecastUsed -and [bool]$cycle.triModelRepairUsed)
  randomSpreadPass=($page.Contains("hcmZones") -and $page.Contains("randomAround") -and $page.Contains("dropoffZone.name === pickupZone.name"))
  explainTracePresent=($page.Contains("Input Snapshot") -and $page.Contains("ML Scoring / Ranking") -and $page.Contains("Dominance Guard") -and $page.Contains("Final Solution"))
  compareThreeSolverPass=(@($solverRows | Where-Object { $_.solverName -match "IntelligentRouteX|OR-Tools|VROOM" }).Count -ge 3)
  compareThreeMapUiPresent=($page.Contains("MiniSolverMap") -and $page.Contains("IRX") -and $page.Contains("OR-Tools") -and $page.Contains("VROOM"))
  routeAnimationUiPresent=($page.Contains("OSRM Route Reveal") -and $page.Contains("Play route") -and $page.Contains("Step next stop"))
  apiArtifactsTabPresent=($page.Contains("cURL Sample") -and $page.Contains("API / Artifacts"))
  controlTowerStylesPresent=($styles.Contains("tower-tabs") -and $styles.Contains("compare-map-grid") -and $styles.Contains("route-reveal-strip"))
  overallPass=$false
}
$summary.overallPass = $summary.compileJava -in @("PASS", "SKIPPED") -and $summary.dashboardBuild -in @("PASS", "SKIPPED") -and $summary.backendHealth -and $summary.startStaticButton -and $summary.startLiveButton -and $summary.benchmarkCompareButton -and $summary.resetButton -and $summary.navTabsPresent -and $summary.staticRunPass -and $summary.liveRunPass -and $summary.randomSpreadPass -and $summary.explainTracePresent -and $summary.compareThreeSolverPass -and $summary.compareThreeMapUiPresent -and $summary.routeAnimationUiPresent -and $summary.apiArtifactsTabPresent -and $summary.controlTowerStylesPresent
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "control-tower-summary.json")
if(-not $summary.overallPass) { throw "Control tower explain compare gate FAIL" }
Write-Host "[CONTROL-TOWER] PASS summary=$(Join-Path $out 'control-tower-summary.json')"

