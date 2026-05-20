param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case", "tight-deadline-case", "driver-imbalanced-case"),
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/seed-source-ablation"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function SourceValue($audit, $source, $field, $default) {
  if ($null -eq $audit -or $null -eq $audit.sources) { return $default }
  $entry = $audit.sources.$source
  if ($null -eq $entry) { return $default }
  $value = $entry.$field
  if ($null -eq $value) { return $default }
  return $value
}

$rows = @()
$artifacts = @()
foreach ($dataset in $Datasets) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $artifact = Join-Path $OutputDir "seed-source-ablation-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $artifacts += $artifact
  $audit = $result.diagnostics.seedSourceAudit
  $ml = $audit.mlGenerated
  $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  $rows += [pscustomobject]@{
    datasetId = $dataset
    jobId = $job.jobId
    runId = $result.runId
    finalSeedSource = $audit.finalSeedSource
    bestSeedSource = $audit.bestSeedSource
    finalKm = [double]$hybrid.totalDistanceKm
    finalLate = [int]$hybrid.lateOrderCount
    mlSeedAttempted = [int]$ml.attempted
    mlSeedCompleted = [int]$ml.completed
    mlSeedFeasible = [int]$ml.feasible
    mlSeedSelectedBest = [int]$ml.selectedAsBestSeed
    mlSeedSelectedFinal = [int]$ml.selectedAsFinalBase
    mlSeedUniqueWin = [int]$ml.uniqueWins
    mlSeedRuntimeMs = [int64]$ml.runtimeMs
    mlSeedRuntimeShare = [double]$ml.runtimeShare
    mlSeedRecommendation = [string]$ml.recommendation
    pyvrpKm = [double](SourceValue $audit "PYVRP_SEED" "distanceKmExact" 0)
    vroomKm = [double](SourceValue $audit "VROOM_SEED" "distanceKmExact" 0)
    ortoolsKm = [double](SourceValue $audit "ORTOOLS_SEED" "distanceKmExact" 0)
    distanceKm = [double](SourceValue $audit "DISTANCE_SEED" "distanceKmExact" 0)
  }
}

$attempted = @($rows | Where-Object { $_.mlSeedAttempted -gt 0 }).Count
$completed = @($rows | Where-Object { $_.mlSeedCompleted -gt 0 }).Count
$feasible = @($rows | Where-Object { $_.mlSeedFeasible -gt 0 }).Count
$best = @($rows | Where-Object { $_.mlSeedSelectedBest -gt 0 }).Count
$final = @($rows | Where-Object { $_.mlSeedSelectedFinal -gt 0 }).Count
$unique = @($rows | Where-Object { $_.mlSeedUniqueWin -gt 0 }).Count
$runtimeMs = ($rows | Measure-Object -Property mlSeedRuntimeMs -Sum).Sum
$avgRuntimeShare = if ($rows.Count -eq 0) { 0.0 } else { (($rows | Measure-Object -Property mlSeedRuntimeShare -Average).Average) }
$recommendation = if ($attempted -eq 0) { "OFF_NO_PRODUCTION_SEED_PRESENT" }
  elseif ($unique -ge 3 -or $final / [math]::Max(1, $rows.Count) -ge 0.10) { "KEEP_PRODUCTION" }
  elseif ($unique -gt 0 -or $final -gt 0) { "DIAGNOSTIC_ONLY" }
  elseif ($avgRuntimeShare -gt 0.10) { "DISABLE_PRODUCTION" }
  else { "DIAGNOSTIC_ONLY" }

$summary = [pscustomobject]@{
  schemaVersion = "seed-source-ablation-gate/v1"
  createdAt = (Get-Date).ToString("o")
  pass = $rows.Count -gt 0
  total = $rows.Count
  mlGenerated = [pscustomobject]@{
    attempted = $attempted
    completed = $completed
    feasible = $feasible
    feasibleRate = if ($attempted -eq 0) { 0.0 } else { $feasible / [double]$attempted }
    selectedAsBestSeed = $best
    selectedAsFinalBase = $final
    uniqueWins = $unique
    runtimeMs = $runtimeMs
    avgRuntimeShare = $avgRuntimeShare
    recommendation = $recommendation
  }
  rows = $rows
  artifacts = $artifacts
}

$summaryPath = Join-Path $OutputDir "seed-source-ablation-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
