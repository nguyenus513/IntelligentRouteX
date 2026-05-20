param(
  [string]$BaseUrl = "http://localhost:8080",
  [string]$RouteFinderBaseUrl = "http://127.0.0.1:8092",
  [string[]]$Datasets = @("raw-s"),
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/routefinder-seed-gate"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$ready = Invoke-RestMethod -Method Get -Uri "$RouteFinderBaseUrl/ready" -TimeoutSec 10
$version = Invoke-RestMethod -Method Get -Uri "$RouteFinderBaseUrl/version" -TimeoutSec 10

$samplePayload = @{
  schemaVersion = "route-request/v1"
  traceId = "routefinder-gate-smoke"
  stageName = "route-proposal-pool"
  timeoutBudgetMs = 5000
  modelContractVersion = "dispatch-v2-ml/v1"
  payload = @{
    schemaVersion = "routefinder-feature-vector/v1"
    traceId = "routefinder-gate-smoke"
    bundleId = "B-GATE"
    anchorOrderId = "ORD-A"
    driverId = "D-GATE"
    baselineSource = "HEURISTIC_FAST"
    baselineStopOrder = @("ORD-A", "ORD-B", "ORD-C")
    bundleOrderIds = @("ORD-A", "ORD-B", "ORD-C")
    projectedPickupEtaMinutes = 10.0
    projectedCompletionEtaMinutes = 25.0
    rerankScore = 0.7
    bundleScore = 0.8
    anchorScore = 0.7
    averagePairSupport = 0.6
    boundaryCross = $false
    maxAlternatives = 2
  }
} | ConvertTo-Json -Depth 20
$refine = Invoke-RestMethod -Method Post -Uri "$RouteFinderBaseUrl/route/refine" -ContentType "application/json" -Body $samplePayload -TimeoutSec 10

$rows = @()
$artifacts = @()
foreach ($dataset in $Datasets) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $artifact = Join-Path $OutputDir "routefinder-seed-gate-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $artifacts += $artifact
  $rf = $result.diagnostics.seedSourceAudit.routefinderProposal
  $rows += [pscustomobject]@{
    datasetId = $dataset
    jobId = $job.jobId
    runId = $result.runId
    routefinderAttempted = [bool]$rf.attempted
    mlProposalCount = [int]$rf.mlProposalCount
    mlRefinedCount = [int]$rf.mlRefinedCount
    selectedMlRefinedCount = [int]$rf.selectedMlRefinedCount
    routeProposalPoolLatencyMs = [int]$rf.routeProposalPoolLatencyMs
    recommendation = [string]$rf.recommendation
  }
}

$attemptedCount = @($rows | Where-Object { $_.routefinderAttempted }).Count
$summary = [pscustomobject]@{
  schemaVersion = "routefinder-seed-gate/v1"
  createdAt = (Get-Date).ToString("o")
  pass = [bool]$ready.ready -and -not [bool]$refine.fallbackUsed -and $attemptedCount -eq $rows.Count
  routefinderReady = [bool]$ready.ready
  routefinderReadyReason = [string]$ready.reason
  version = $version
  smokeRefineFallbackUsed = [bool]$refine.fallbackUsed
  smokeRefineRouteCount = @($refine.payload.routes).Count
  total = $rows.Count
  attemptedCount = $attemptedCount
  rows = $rows
  artifacts = $artifacts
}

$summaryPath = Join-Path $OutputDir "routefinder-seed-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
