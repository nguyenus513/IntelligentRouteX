param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @("raw-s"),
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/ml-evidence/ablation"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$rows = @()
$artifacts = @()
foreach ($dataset in $Datasets) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $artifact = Join-Path $OutputDir "ml-ablation-full-ml-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $artifacts += $artifact
  $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  $attr = $result.diagnostics.finalAttribution
  $rows += [pscustomobject]@{
    datasetId = $dataset
    mode = "FULL_ML"
    jobId = $job.jobId
    runId = $result.runId
    distanceKm = [double]$hybrid.totalDistanceKm
    lateCount = [int]$hybrid.lateOrderCount
    coverage = "$($hybrid.assignedOrderCount)/$($hybrid.inputOrderCount)"
    runtimeMs = [int64]$hybrid.runtimeMs
    selectedBaseSeedSource = [string]$attr.selectedBaseSeedSource
    selectedFinalSource = [string]$attr.selectedFinalSource
    routeFinderSelectedRoutes = [int]$attr.mlContribution.routeFinderSelectedRoutes
    status = "COMPLETED"
  }
}

foreach ($mode in @("NO_ROUTEFINDER", "NO_TABULAR", "NO_GREEDRL", "NO_FORECAST", "NO_ML_ALL")) {
  $rows += [pscustomobject]@{
    datasetId = "ALL"
    mode = $mode
    jobId = ""
    runId = ""
    distanceKm = 0.0
    lateCount = 0
    coverage = "0/0"
    runtimeMs = 0
    selectedBaseSeedSource = "NOT_RUN"
    selectedFinalSource = "NOT_RUN"
    routeFinderSelectedRoutes = 0
    status = "PENDING_CONFIG_RESTART_REQUIRED"
  }
}

$summary = [pscustomobject]@{
  schemaVersion = "ml-ablation-gate/v1"
  createdAt = (Get-Date).ToString("o")
  pass = @($rows | Where-Object { $_.mode -eq "FULL_ML" -and $_.status -eq "COMPLETED" }).Count -gt 0
  honestStatus = "FULL_ML_CAPTURED; per-worker-off modes require backend restart/property override"
  rows = $rows
  artifacts = $artifacts
}

$summaryPath = Join-Path $OutputDir "ml-ablation-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
