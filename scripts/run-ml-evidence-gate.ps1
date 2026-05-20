param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "tight-deadline-case", "driver-scarcity-case", "driver-imbalanced-case"),
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/ml-evidence-gate"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Role($evidence, $name, $field, $default) {
  if ($null -eq $evidence) { return $default }
  $role = $evidence.$name
  if ($null -eq $role) { return $default }
  $value = $role.$field
  if ($null -eq $value) { return $default }
  return $value
}

$rows = @()
$artifacts = @()
foreach ($dataset in $Datasets) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $artifact = Join-Path $OutputDir "ml-evidence-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $artifacts += $artifact
  $e = $result.diagnostics.mlEvidence
  $rows += [pscustomobject]@{
    datasetId = $dataset
    jobId = $job.jobId
    runId = $result.runId
    tabularInvocations = [int](Role $e "tabular" "invocations" 0)
    tabularRecommendation = [string](Role $e "tabular" "recommendation" "MISSING")
    routeFinderInvocations = [int](Role $e "routeFinder" "invocations" 0)
    routeFinderRefined = [int](Role $e "routeFinder" "refinedProposals" 0)
    routeFinderSelected = [int](Role $e "routeFinder" "selectedMlRefinedCount" 0)
    routeFinderRecommendation = [string](Role $e "routeFinder" "recommendation" "MISSING")
    greedRlInvocations = [int](Role $e "greedRl" "invocations" 0)
    greedRlRecommendation = [string](Role $e "greedRl" "recommendation" "MISSING")
    forecastInvocations = [int](Role $e "forecast" "invocations" 0)
    forecastSkipReason = [string](Role $e "forecast" "skipReason" "")
    forecastRecommendation = [string](Role $e "forecast" "recommendation" "MISSING")
  }
}

$summary = [pscustomobject]@{
  schemaVersion = "ml-evidence-gate/v1"
  createdAt = (Get-Date).ToString("o")
  pass = $rows.Count -gt 0 -and @($rows | Where-Object { $_.routeFinderSelected -gt 0 }).Count -gt 0
  total = $rows.Count
  tabularInvocations = ($rows | Measure-Object -Property tabularInvocations -Sum).Sum
  routeFinderInvocations = ($rows | Measure-Object -Property routeFinderInvocations -Sum).Sum
  routeFinderSelected = ($rows | Measure-Object -Property routeFinderSelected -Sum).Sum
  greedRlInvocations = ($rows | Measure-Object -Property greedRlInvocations -Sum).Sum
  forecastInvocations = ($rows | Measure-Object -Property forecastInvocations -Sum).Sum
  recommendations = [pscustomobject]@{
    tabular = if ((($rows | Measure-Object -Property tabularInvocations -Sum).Sum) -gt 0) { "KEEP_OR_ABLATE" } else { "NEEDS_INVOCATION_GATE" }
    routeFinder = if ((($rows | Measure-Object -Property routeFinderSelected -Sum).Sum) -gt 0) { "KEEP" } else { "NEEDS_GATE" }
    greedRl = if ((($rows | Measure-Object -Property greedRlInvocations -Sum).Sum) -gt 0) { "KEEP_OR_ABLATE" } else { "NEEDS_COMPLEX_DATASET" }
    forecast = if ((($rows | Measure-Object -Property forecastInvocations -Sum).Sum) -gt 0) { "KEEP_OR_ABLATE" } else { "RUN_FORECAST_GATE" }
  }
  rows = $rows
  artifacts = $artifacts
}

$summaryPath = Join-Path $OutputDir "ml-evidence-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
