param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s"),
  [string[]]$Modes = @("HEURISTIC_IMPROVER", "ADAPTIVE_ML_POLICY_DIAGNOSTIC", "ADAPTIVE_ML_POLICY_TIE_BREAK", "ADAPTIVE_ML_POLICY_TOP_K", "ADAPTIVE_ML_POLICY_LEARNED_ROUND_1", "ADAPTIVE_ML_POLICY_LEARNED_ROUND_2", "ADAPTIVE_ML_POLICY_LEARNED_ROUND_3"),
  [switch]$PersistenceEnabled,
  [string]$StatePath = "artifacts/adaptive-ml/adaptive-learning-state.json",
  [int]$TopKMoves = 30,
  [double]$ExplorationRate = 0.10,
  [int]$QualityBudgetMs = 0,
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/adaptive-ml-policy"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Role($diagnostics, $field, $default) {
  if ($null -eq $diagnostics) { return $default }
  $value = $diagnostics.$field
  if ($null -eq $value) { return $default }
  return $value
}

function RequestMode($mode) {
  switch ($mode) {
    "HEURISTIC_IMPROVER" { return "DIAGNOSTIC" }
    "ADAPTIVE_ML_POLICY_DIAGNOSTIC" { return "DIAGNOSTIC" }
    "ADAPTIVE_ML_POLICY_TIE_BREAK" { return "TIE_BREAK" }
    "ADAPTIVE_ML_POLICY_TOP_K" { return "TOP_K_ASSISTED" }
    "ADAPTIVE_ML_POLICY_QUALITY_SEEKING" { return "QUALITY_SEEKING" }
    "ADAPTIVE_ML_POLICY_LEARNED_ROUND_1" { return "TOP_K_ASSISTED" }
    "ADAPTIVE_ML_POLICY_LEARNED_ROUND_2" { return "TOP_K_ASSISTED" }
    "ADAPTIVE_ML_POLICY_LEARNED_ROUND_3" { return "TOP_K_ASSISTED" }
    default { return "DIAGNOSTIC" }
  }
}

function Run-Dataset($mode, $dataset) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; adaptiveMlPolicyMode = (RequestMode $mode); adaptiveTopKMoves = $TopKMoves; adaptiveExplorationRate = $ExplorationRate; adaptiveQualityBudgetMs = $QualityBudgetMs; adaptivePersistenceEnabled = [bool]$PersistenceEnabled; adaptiveStatePath = $StatePath; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec $DatasetTimeoutSeconds
  $artifact = Join-Path $OutputDir "adaptive-$mode-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  $adaptive = $result.diagnostics.seedImprovement.adaptiveMlPolicy
  $movePriority = Role $adaptive "adaptiveMovePriority" $null
  $reward = Role $adaptive "rewardUpdate" $null
  $dominancePassed = $true
  if ($null -ne $result.diagnostics.externalSeedDominance -and $null -ne $result.diagnostics.externalSeedDominance.passed) {
    $dominancePassed = [bool]$result.diagnostics.externalSeedDominance.passed
  }
  return [pscustomobject]@{
    mode = $mode
    datasetId = $dataset
    jobId = $job.jobId
    runId = $result.runId
    distanceKm = [double]$hybrid.totalDistanceKm
    lateCount = [int]$hybrid.lateOrderCount
    assignedCount = [int]$hybrid.assignedOrderCount
    inputOrderCount = [int]$hybrid.inputOrderCount
    coverage = "$($hybrid.assignedOrderCount)/$($hybrid.inputOrderCount)"
    runtimeMs = [int64]$hybrid.runtimeMs
    evaluatedMoves = [int](Role $movePriority "evaluatedTopK" 0)
    scoredMoves = [int](Role $movePriority "scoredMoves" 0)
    acceptedMoves = [int](Role $movePriority "acceptedMoves" 0)
    acceptedMoveRate = [double](Role $movePriority "acceptedMoveRate" 0.0)
    rewardTotal = [double](Role $reward "rewardTotal" 0.0)
    requestedMode = [string](Role $adaptive "requestedMode" "MISSING")
    effectiveMode = [string](Role $adaptive "effectiveMode" "MISSING")
    selectionControlApplied = [bool](Role $adaptive "selectionControlApplied" $false)
    moveOrderingApplied = [bool](Role $adaptive "moveOrderingApplied" $false)
    topKApplied = [bool](Role $adaptive "topKApplied" $false)
    dominanceFailures = if ($dominancePassed) { 0 } else { 1 }
    lateRegression = 0
    qualityNoWorseThanHeuristic = $null
    gainType = "PENDING_BASELINE_COMPARE"
    adaptiveDiagnosticsPresent = $null -ne $adaptive
    artifact = $artifact
  }
}

function Compare-Row($row, $baseline) {
  if ($null -eq $row -or $null -eq $baseline) { return $row }
  $qualityNoWorse = [double]$row.distanceKm -le [double]$baseline.distanceKm -and [int]$row.lateCount -le [int]$baseline.lateCount -and [string]$row.coverage -eq [string]$baseline.coverage -and [int]$row.dominanceFailures -eq 0
  $gainTypes = @()
  if ([double]$row.distanceKm -lt [double]$baseline.distanceKm) { $gainTypes += "DISTANCE" }
  if ([int]$row.lateCount -lt [int]$baseline.lateCount) { $gainTypes += "LATE" }
  if ([int64]$row.runtimeMs -lt [int64]$baseline.runtimeMs) { $gainTypes += "RUNTIME" }
  if ([int]$row.evaluatedMoves -lt [int]$baseline.evaluatedMoves) { $gainTypes += "EVALUATED_MOVES" }
  if ([double]$row.acceptedMoveRate -gt [double]$baseline.acceptedMoveRate) { $gainTypes += "ACCEPTED_MOVE_RATE" }
  $row.lateRegression = [int]$row.lateCount - [int]$baseline.lateCount
  $row.qualityNoWorseThanHeuristic = $qualityNoWorse
  $row.gainType = if ($gainTypes.Count -gt 0) { $gainTypes -join "+" } else { "NONE" }
  return $row
}

$rows = @()
foreach ($dataset in $Datasets) {
  foreach ($mode in $Modes) {
    $rows += Run-Dataset $mode $dataset
  }
}

$comparedRows = @()
foreach ($dataset in $Datasets) {
  $baseline = $rows | Where-Object { $_.datasetId -eq $dataset -and $_.mode -eq "HEURISTIC_IMPROVER" } | Select-Object -First 1
  foreach ($row in @($rows | Where-Object datasetId -eq $dataset)) {
    if ($row.mode -eq "HEURISTIC_IMPROVER") {
      $row.qualityNoWorseThanHeuristic = $true
      $row.gainType = "BASELINE"
      $comparedRows += $row
    } else {
      $comparedRows += Compare-Row $row $baseline
    }
  }
}
$rows = $comparedRows

$heuristic = $rows | Where-Object mode -eq "HEURISTIC_IMPROVER" | Select-Object -First 1
$learned = $rows | Where-Object mode -eq "ADAPTIVE_ML_POLICY_LEARNED_ROUND_3" | Select-Object -First 1
if ($null -eq $learned) { $learned = $rows | Where-Object mode -eq "ADAPTIVE_ML_POLICY_TOP_K" | Select-Object -First 1 }
if ($null -eq $learned) { $learned = $rows | Where-Object mode -ne "HEURISTIC_IMPROVER" | Select-Object -Last 1 }
$diagnosticsComplete = ($rows | Where-Object { -not $_.adaptiveDiagnosticsPresent }).Count -eq 0
$notWorseQuality = $learned -and $heuristic -and [double]$learned.distanceKm -le [double]$heuristic.distanceKm -and [int]$learned.lateCount -le [int]$heuristic.lateCount -and [string]$learned.coverage -eq [string]$heuristic.coverage
$hasObservedBenefit = $learned -and $heuristic -and (
  [double]$learned.distanceKm -lt [double]$heuristic.distanceKm -or
  [int]$learned.lateCount -lt [int]$heuristic.lateCount -or
  [int64]$learned.runtimeMs -lt [int64]$heuristic.runtimeMs -or
  [int]$learned.evaluatedMoves -lt [int]$heuristic.evaluatedMoves -or
  [double]$learned.acceptedMoveRate -gt [double]$heuristic.acceptedMoveRate
)
$adaptiveRows = @($rows | Where-Object { $_.mode -ne "HEURISTIC_IMPROVER" })
$isolatedModeControl = @($adaptiveRows | Where-Object { ($_.effectiveMode -eq "TOP_K_ASSISTED" -or $_.effectiveMode -eq "QUALITY_SEEKING") -and $_.topKApplied -eq $true }).Count -gt 0
$noWorseCount = @($adaptiveRows | Where-Object { $_.qualityNoWorseThanHeuristic -eq $true }).Count
$gainCount = @($adaptiveRows | Where-Object { $_.gainType -ne "NONE" -and $_.gainType -ne "BASELINE" }).Count
$lossCount = @($adaptiveRows | Where-Object { $_.qualityNoWorseThanHeuristic -ne $true }).Count
$moveOrderingAppliedCount = @($adaptiveRows | Where-Object { $_.moveOrderingApplied -eq $true }).Count
$topKAppliedCount = @($adaptiveRows | Where-Object { $_.topKApplied -eq $true }).Count

$summary = [pscustomobject]@{
  schemaVersion = "adaptive-ml-policy-gate/v1"
  createdAt = (Get-Date).ToString("o")
  overallPass = [bool]($notWorseQuality -and $diagnosticsComplete -and $lossCount -eq 0)
  verdict = if (-not $diagnosticsComplete) { "ADAPTIVE_ML_DIAGNOSTICS_MISSING" } elseif ($isolatedModeControl -and $notWorseQuality -and $hasObservedBenefit) { "ADAPTIVE_ML_POLICY_ACCEPTED" } elseif ($notWorseQuality) { "ADAPTIVE_ML_POLICY_DIAGNOSTIC_PASS" } else { "ADAPTIVE_ML_POLICY_DIAGNOSTIC_ONLY" }
  isolatedModeControl = $isolatedModeControl
  modeControlNote = if ($isolatedModeControl) { "Backend applied assisted effective mode for at least one adaptive row; assisted acceptance still requires no-loss plus observed gain." } else { "Rows request adaptiveMlPolicyMode, but backend did not apply assisted mode; assisted causality requires effectiveMode=TOP_K_ASSISTED and topKApplied=true." }
  benefitObservedWithoutIsolation = [bool]$hasObservedBenefit
  heuristic = $heuristic
  adaptiveLearned = $learned
  gain = if ($heuristic -and $learned) { [pscustomobject]@{
    distanceGainKm = [math]::Round(([double]$heuristic.distanceKm - [double]$learned.distanceKm), 3)
    lateRegression = [int]$learned.lateCount - [int]$heuristic.lateCount
    runtimeReductionMs = [int64]$heuristic.runtimeMs - [int64]$learned.runtimeMs
    evaluatedMoveReduction = [int]$heuristic.evaluatedMoves - [int]$learned.evaluatedMoves
    acceptedMoveRateGain = [math]::Round(([double]$learned.acceptedMoveRate - [double]$heuristic.acceptedMoveRate), 3)
  }} else { $null }
  rows = $rows
  aggregate = [pscustomobject]@{
    datasets = $Datasets.Count
    adaptiveRows = $adaptiveRows.Count
    noWorseCount = $noWorseCount
    gainCount = $gainCount
    lossCount = $lossCount
    lateRegressionCount = @($adaptiveRows | Where-Object { $_.lateRegression -gt 0 }).Count
    dominanceFailureCount = @($adaptiveRows | Where-Object { $_.dominanceFailures -gt 0 }).Count
    moveOrderingAppliedCount = $moveOrderingAppliedCount
    topKAppliedCount = $topKAppliedCount
  }
}

$summaryPath = Join-Path $OutputDir "adaptive-ml-policy-summary.json"
$summary | ConvertTo-Json -Depth 30 | Set-Content $summaryPath
$final = [pscustomobject]@{
  schemaVersion = "adaptive-ml-policy-final-summary/v1"
  createdAt = (Get-Date).ToString("o")
  overallPass = $summary.overallPass
  verdict = if ($summary.overallPass -and $isolatedModeControl -and $moveOrderingAppliedCount -eq $adaptiveRows.Count -and $gainCount -gt 0) { "ADAPTIVE_ML_POLICY_MOVE_ORDERING_ACCEPTED" } elseif ($summary.overallPass -and $isolatedModeControl -and $gainCount -gt 0) { "ADAPTIVE_ML_POLICY_ASSISTED_ACCEPTED" } elseif ($summary.overallPass) { "ADAPTIVE_ML_POLICY_DIAGNOSTIC_PASS_ASSISTED_NOT_ISOLATED" } else { "ADAPTIVE_ML_POLICY_DIAGNOSTIC_ONLY" }
  assistedAccepted = [bool]($summary.overallPass -and $isolatedModeControl -and $gainCount -gt 0)
  moveOrderingAccepted = [bool]($summary.overallPass -and $isolatedModeControl -and $moveOrderingAppliedCount -eq $adaptiveRows.Count -and $gainCount -gt 0)
  diagnosticPass = [bool]$summary.overallPass
  aggregate = $summary.aggregate
  modeControlNote = $summary.modeControlNote
  summary = $summaryPath
}
$finalPath = Join-Path $OutputDir "adaptive-ml-policy-final-summary.json"
$final | ConvertTo-Json -Depth 20 | Set-Content $finalPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
Write-Output "FINAL_SUMMARY=$finalPath"
if (-not $summary.overallPass) { exit 1 }




