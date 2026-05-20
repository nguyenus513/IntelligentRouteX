param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s"),
  [int]$Port = 18116,
  [int]$StartupTimeoutSeconds = 90,
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/ml-evidence/ablation-restart"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path "artifacts/logs" | Out-Null

function Stop-Backend() {
  Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like "*server.port=$Port*" -or $_.CommandLine -like "*gradlew.bat bootRun*" -or $_.CommandLine -like "*RouteChainApiApplication*") -and $_.ProcessId -ne $PID
  } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep -Seconds 2
}

function Start-Backend($mode, $overrides) {
  $env:GRADLE_USER_HOME = (Resolve-Path '.').Path + '\.gradle-tmp'
  if (Test-Path '.\tools\vroom\vroom-wsl.cmd') { $env:VROOM_BIN = (Resolve-Path '.\tools\vroom\vroom-wsl.cmd').Path }
  $log = (Resolve-Path '.').Path + "\artifacts\logs\bootrun-ml-ablation-$mode.log"
  $err = "$log.err"
  $args = "--server.port=$Port $overrides"
  $cmd = 'set GRADLE_USER_HOME=' + $env:GRADLE_USER_HOME + '&& set VROOM_BIN=' + $env:VROOM_BIN + '&& gradlew.bat bootRun --no-daemon --args="' + $args + '"'
  Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $cmd) -RedirectStandardOutput $log -RedirectStandardError $err | Out-Null
  $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    try {
      Invoke-RestMethod "http://localhost:$Port/api/v1/dispatch/health" -TimeoutSec 2 | Out-Null
      return @{ log = $log; err = $err }
    } catch {}
  }
  throw "backend-start-timeout:$mode log=$log err=$err"
}

function Run-Dataset($mode, $dataset) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $modeDir = Join-Path $OutputDir $mode
  New-Item -ItemType Directory -Force -Path $modeDir | Out-Null
  $artifact = Join-Path $modeDir "ml-ablation-$mode-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  $attr = $result.diagnostics.finalAttribution
  $ml = $result.diagnostics.mlEvidence
  return [pscustomobject]@{
    datasetId = $dataset
    mode = $mode
    jobId = $job.jobId
    runId = $result.runId
    distanceKm = [double]$hybrid.totalDistanceKm
    lateCount = [int]$hybrid.lateOrderCount
    coverage = "$($hybrid.assignedOrderCount)/$($hybrid.inputOrderCount)"
    runtimeMs = [int64]$hybrid.runtimeMs
    selectedBaseSeedSource = [string]$attr.selectedBaseSeedSource
    selectedFinalSource = [string]$attr.selectedFinalSource
    routeFinderSelectedRoutes = [int]$attr.mlContribution.routeFinderSelectedRoutes
    tabularInvocations = [int]$ml.tabular.invocations
    routeFinderInvocations = [int]$ml.routeFinder.invocations
    greedRlInvocations = [int]$ml.greedRl.invocations
    forecastInvocations = [int]$ml.forecast.invocations
    coverageDrainOrRepairCount = [int]$attr.coverageDrainOrRepairCount
    artifact = $artifact
  }
}

$modes = @(
  @{ name = "FULL_ML"; overrides = "" },
  @{ name = "NO_ROUTEFINDER"; overrides = "--routechain.dispatch-v2.ml.routefinder.enabled=false" },
  @{ name = "NO_TABULAR"; overrides = "--routechain.dispatch-v2.ml.tabular.enabled=false" },
  @{ name = "NO_GREEDRL"; overrides = "--routechain.dispatch-v2.ml.greedrl.enabled=false" },
  @{ name = "NO_FORECAST"; overrides = "--routechain.dispatch-v2.ml.forecast.enabled=false" },
  @{ name = "NO_ML_ALL"; overrides = "--routechain.dispatch-v2.ml-enabled=false --routechain.dispatch-v2.sidecar-required=false" }
)

$rows = @()
$startLogs = @()
foreach ($mode in $modes) {
  Stop-Backend
  $start = Start-Backend $mode.name $mode.overrides
  $startLogs += [pscustomobject]@{ mode = $mode.name; log = $start.log; err = $start.err; overrides = $mode.overrides }
  foreach ($dataset in $Datasets) {
    $rows += Run-Dataset $mode.name $dataset
  }
}
Stop-Backend

$full = $rows | Where-Object mode -eq "FULL_ML" | Select-Object -First 1
function Delta($mode) {
  $row = $rows | Where-Object mode -eq $mode | Select-Object -First 1
  if ($null -eq $full -or $null -eq $row) { return $null }
  return [pscustomobject]@{
    mode = $mode
    distanceDeltaKm = [math]::Round(([double]$row.distanceKm - [double]$full.distanceKm), 3)
    lateDelta = [int]$row.lateCount - [int]$full.lateCount
    runtimeDeltaMs = [int64]$row.runtimeMs - [int64]$full.runtimeMs
  }
}

$deltas = @("NO_ROUTEFINDER", "NO_TABULAR", "NO_GREEDRL", "NO_FORECAST", "NO_ML_ALL") | ForEach-Object { Delta $_ }
$summary = [pscustomobject]@{
  schemaVersion = "ml-ablation-restart-summary/v1"
  createdAt = (Get-Date).ToString("o")
  pass = $rows.Count -eq ($modes.Count * $Datasets.Count)
  datasets = $Datasets
  rows = $rows
  deltasVsFullMl = $deltas
  decisions = [pscustomobject]@{
    routeFinder = if ((($deltas | Where-Object mode -eq "NO_ROUTEFINDER").distanceDeltaKm) -gt 0 -or $full.routeFinderSelectedRoutes -gt 0) { "KEEP" } else { "DIAGNOSTIC_ONLY" }
    tabular = if ((($deltas | Where-Object mode -eq "NO_TABULAR").distanceDeltaKm) -gt 0 -or (($deltas | Where-Object mode -eq "NO_TABULAR").lateDelta) -gt 0) { "KEEP" } else { "DIAGNOSTIC_ONLY" }
    greedRl = if ((($deltas | Where-Object mode -eq "NO_GREEDRL").distanceDeltaKm) -gt 0 -or (($deltas | Where-Object mode -eq "NO_GREEDRL").lateDelta) -gt 0) { "KEEP" } else { "COMPLEX_ONLY" }
    forecast = if ((($deltas | Where-Object mode -eq "NO_FORECAST").lateDelta) -gt 0) { "KEEP" } else { "LIVE_RESCUE_ONLY" }
    mlGeneratedSeed = "OFF"
  }
  startLogs = $startLogs
}

$summaryPath = Join-Path $OutputDir "ml-ablation-restart-summary.json"
$summary | ConvertTo-Json -Depth 30 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }

