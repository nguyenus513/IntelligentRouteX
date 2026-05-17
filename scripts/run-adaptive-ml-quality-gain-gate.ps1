param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [string]$StatePath = "artifacts/adaptive-ml/adaptive-learning-state.json",
  [string]$BaselineStatePath = "artifacts/adaptive-ml/adaptive-learning-state-v0.9.8-baseline.json",
  [string]$OutputDir = "artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-gain",
  [string]$Mode = "TOP_K_ASSISTED",
  [int]$TopKMoves = 80,
  [double]$ExplorationRate = 0.20,
  [int]$QualityBudgetMs = 5000,
  [int]$DatasetTimeoutSeconds = 360,
  [switch]$RunQuality20OnCandidate
)

$ErrorActionPreference = "Stop"
$AllQualityDatasets = @(
  "raw-s",
  "raw-m",
  "random-spread",
  "driver-scarcity-case",
  "tight-deadline-case",
  "wide-deadline-case",
  "driver-imbalanced-case",
  "many-orders-few-drivers",
  "few-orders-many-drivers",
  "opposite-direction-dropoffs",
  "clustered-pickups-random-dropoffs",
  "random-pickups-clustered-dropoffs",
  "long-tail-distance",
  "tight-capacity",
  "high-priority-orders",
  "active-route-insertion",
  "driver-location-shift",
  "deferred-order-aging",
  "rescue-like-rebalance",
  "high-density-lunch-rush"
)
if ($Datasets.Count -eq 1 -and ($Datasets[0] -eq "all" -or $Datasets[0] -eq "quality-20")) {
  $Datasets = $AllQualityDatasets
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $StatePath -Parent) | Out-Null

if ((Test-Path $StatePath) -and -not (Test-Path $BaselineStatePath)) {
  Copy-Item $StatePath $BaselineStatePath -Force
}
if (Test-Path $BaselineStatePath) {
  Copy-Item $BaselineStatePath $StatePath -Force
}

function ReadJson($path) {
  if (-not (Test-Path $path)) { return $null }
  return Get-Content $path -Raw | ConvertFrom-Json
}

function PolicyRowName() { if ($Mode -eq "QUALITY_SEEKING") { return "ADAPTIVE_ML_POLICY_QUALITY_SEEKING" } return "ADAPTIVE_ML_POLICY_TOP_K" }

function Invoke-PolicyGate($name, $topKMoves, $explorationRate, $qualityBudgetMs) {
  $runDir = Join-Path $OutputDir $name
  & scripts/run-adaptive-ml-policy-gate.ps1 `
    -BaseUrl $BaseUrl `
    -Datasets $Datasets `
    -Modes @("HEURISTIC_IMPROVER", (PolicyRowName)) `
    -PersistenceEnabled `
    -StatePath $StatePath `
    -TopKMoves $topKMoves `
    -ExplorationRate $explorationRate `
    -QualityBudgetMs $qualityBudgetMs `
    -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
    -OutputDir $runDir | Out-Host
  $summary = ReadJson (Join-Path $runDir "adaptive-ml-policy-summary.json")
  $final = ReadJson (Join-Path $runDir "adaptive-ml-policy-final-summary.json")
  if ($null -eq $summary -or $null -eq $final) { throw "missing-policy-gate-summary-$name" }
  return [pscustomobject]@{ name = $name; mode = $Mode; topKMoves = $topKMoves; explorationRate = $explorationRate; qualityBudgetMs = $qualityBudgetMs; dir = $runDir; summary = $summary; final = $final }
}

function Build-QualityRows($run) {
  $rows = @()
  foreach ($dataset in $Datasets) {
    $heuristic = $run.summary.rows | Where-Object { $_.datasetId -eq $dataset -and $_.mode -eq "HEURISTIC_IMPROVER" } | Select-Object -First 1
    $adaptive = $run.summary.rows | Where-Object { $_.datasetId -eq $dataset -and $_.mode -ne "HEURISTIC_IMPROVER" } | Select-Object -First 1
    if ($null -eq $heuristic -or $null -eq $adaptive) { continue }
    $distanceGain = [math]::Round([double]$heuristic.distanceKm - [double]$adaptive.distanceKm, 3)
    $lateReduction = [int]$heuristic.lateCount - [int]$adaptive.lateCount
    $coverageSame = [string]$heuristic.coverage -eq [string]$adaptive.coverage
    $noWorse = $coverageSame -and [int]$adaptive.dominanceFailures -eq 0 -and [double]$adaptive.distanceKm -le [double]$heuristic.distanceKm -and [int]$adaptive.lateCount -le [int]$heuristic.lateCount
    $qualityGain = $distanceGain -gt 0 -or $lateReduction -gt 0
    $runtimeReduction = [int64]$heuristic.runtimeMs - [int64]$adaptive.runtimeMs
    $rows += [pscustomobject]@{
      datasetId = $dataset
      heuristicDistanceKm = [double]$heuristic.distanceKm
      adaptiveDistanceKm = [double]$adaptive.distanceKm
      distanceGainKm = $distanceGain
      heuristicLateCount = [int]$heuristic.lateCount
      adaptiveLateCount = [int]$adaptive.lateCount
      lateReduction = $lateReduction
      coverageSame = [bool]$coverageSame
      dominanceFailures = [int]$adaptive.dominanceFailures
      runtimeReductionMs = $runtimeReduction
      qualityNoWorse = [bool]$noWorse
      qualityGain = [bool]$qualityGain
      effectiveMode = [string]$adaptive.effectiveMode
      moveOrderingApplied = [bool]$adaptive.moveOrderingApplied
      topKApplied = [bool]$adaptive.topKApplied
      gainType = [string]$adaptive.gainType
    }
  }
  return @($rows)
}

$runs = @()
$runs += Invoke-PolicyGate "baseline-state" $TopKMoves $ExplorationRate $QualityBudgetMs
if (Test-Path $BaselineStatePath) { Copy-Item $BaselineStatePath $StatePath -Force }
$runs += Invoke-PolicyGate "more-budget" ([Math]::Max($TopKMoves, 120)) ([Math]::Max($ExplorationRate, 0.25)) ([Math]::Max($QualityBudgetMs, 8000))
if (Test-Path $BaselineStatePath) { Copy-Item $BaselineStatePath $StatePath -Force }
$runs += Invoke-PolicyGate "more-explore" ([Math]::Max($TopKMoves, 80)) ([Math]::Max($ExplorationRate, 0.40)) ([Math]::Max($QualityBudgetMs, 8000))

$runSummaries = @()
foreach ($run in $runs) {
  $qualityRows = Build-QualityRows $run
  $qualityGainCases = @($qualityRows | Where-Object qualityGain -eq $true).Count
  $lossCases = @($qualityRows | Where-Object qualityNoWorse -ne $true).Count
  $lateRegression = @($qualityRows | Where-Object { $_.lateReduction -lt 0 }).Count
  $dominanceFailures = @($qualityRows | Where-Object { $_.dominanceFailures -gt 0 }).Count
  $coverageRegression = @($qualityRows | Where-Object coverageSame -ne $true).Count
  $distanceGainTotal = [math]::Round([double](($qualityRows | Measure-Object -Property distanceGainKm -Sum).Sum), 3)
  $runtimeReductionTotal = [int64](($qualityRows | Measure-Object -Property runtimeReductionMs -Sum).Sum)
  $runSummaries += [pscustomobject]@{
    name = $run.name
    topKMoves = $run.topKMoves
    explorationRate = $run.explorationRate
    overallPass = [bool]($lossCases -eq 0 -and $lateRegression -eq 0 -and $dominanceFailures -eq 0 -and $coverageRegression -eq 0)
    qualityGainCases = $qualityGainCases
    distanceGainKm = $distanceGainTotal
    lateReduction = [int](($qualityRows | Measure-Object -Property lateReduction -Sum).Sum)
    runtimeReductionMs = $runtimeReductionTotal
    lossCases = $lossCases
    lateRegressionCount = $lateRegression
    dominanceFailureCount = $dominanceFailures
    coverageRegressionCount = $coverageRegression
    moveOrderingAppliedCount = @($qualityRows | Where-Object moveOrderingApplied -eq $true).Count
    topKAppliedCount = @($qualityRows | Where-Object topKApplied -eq $true).Count
    rows = $qualityRows
    summary = Join-Path $run.dir "adaptive-ml-policy-summary.json"
    finalSummary = Join-Path $run.dir "adaptive-ml-policy-final-summary.json"
  }
}

$candidates = @($runSummaries | Where-Object { $_.overallPass -eq $true -and $_.qualityGainCases -gt 0 })
$best = $candidates | Sort-Object -Property qualityGainCases, distanceGainKm, runtimeReductionMs -Descending | Select-Object -First 1
$runtimeOnly = $runSummaries | Sort-Object -Property runtimeReductionMs -Descending | Select-Object -First 1
$selected = if ($best) { $best } else { $runtimeOnly }
$qualityAccepted = $null -ne $best

$quality20 = $null
if ($qualityAccepted -and $RunQuality20OnCandidate) {
  $quality20Dir = Join-Path $OutputDir "quality-20"
  & scripts/run-adaptive-ml-policy-gate.ps1 `
    -BaseUrl $BaseUrl `
    -Datasets @("quality-20") `
    -Modes @("HEURISTIC_IMPROVER", (PolicyRowName)) `
    -PersistenceEnabled `
    -StatePath $StatePath `
    -TopKMoves $selected.topKMoves `
    -ExplorationRate $selected.explorationRate `
    -QualityBudgetMs $selected.qualityBudgetMs `
    -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
    -OutputDir $quality20Dir | Out-Host
  $quality20Summary = ReadJson (Join-Path $quality20Dir "adaptive-ml-policy-summary.json")
  $quality20Final = ReadJson (Join-Path $quality20Dir "adaptive-ml-policy-final-summary.json")
  $quality20 = [pscustomobject]@{ summary = Join-Path $quality20Dir "adaptive-ml-policy-summary.json"; finalSummary = Join-Path $quality20Dir "adaptive-ml-policy-final-summary.json"; overallPass = $quality20Final.overallPass; aggregate = $quality20Final.aggregate }
}

$overallPass = [bool]($qualityAccepted -and ($null -eq $quality20 -or $quality20.overallPass -eq $true))
$verdict = if ($overallPass) { "ADAPTIVE_ML_QUALITY_GAIN_ACCEPTED" } elseif ($selected -and $selected.overallPass -and $selected.runtimeReductionMs -gt 0) { "ADAPTIVE_ML_RUNTIME_GAIN_ONLY" } elseif ($selected -and -not $selected.overallPass) { "ADAPTIVE_ML_QUALITY_REGRESSION" } else { "ADAPTIVE_NO_QUALITY_GAIN" }

$out = [pscustomobject]@{
  schemaVersion = "adaptive-ml-quality-gain-summary/v1"
  createdAt = (Get-Date).ToString("o")
  overallPass = $overallPass
  verdict = $verdict
  statePath = $StatePath
  baselineStatePath = $BaselineStatePath
  selectedRun = $selected.name
  qualityGain = [pscustomobject]@{
    distanceGainKm = if ($selected) { $selected.distanceGainKm } else { 0.0 }
    lateReduction = if ($selected) { $selected.lateReduction } else { 0 }
    totalLatenessReduction = 0
    improvedCases = if ($selected) { $selected.qualityGainCases } else { 0 }
    lossCases = if ($selected) { $selected.lossCases } else { 0 }
  }
  guards = [pscustomobject]@{
    lateRegression = if ($selected) { $selected.lateRegressionCount } else { 0 }
    dominanceFailures = if ($selected) { $selected.dominanceFailureCount } else { 0 }
    coverageRegression = if ($selected) { $selected.coverageRegressionCount } else { 0 }
  }
  runtime = [pscustomobject]@{
    runtimeReductionMs = if ($selected) { $selected.runtimeReductionMs } else { 0 }
  }
  runs = $runSummaries
  quality20 = $quality20
  recommendation = if ($overallPass) { "tag v0.9.9 only after reviewing quality-20 if required" } elseif ($verdict -eq "ADAPTIVE_ML_RUNTIME_GAIN_ONLY") { "keep v0.9.8 runtime-learning profile; do not claim quality improvement" } else { "rollback to v0.9.8 state and reduce exploration/adaptive budget" }
}

$summaryPath = Join-Path $OutputDir "adaptive-ml-quality-gain-summary.json"
$out | ConvertTo-Json -Depth 40 | Set-Content $summaryPath
$runSummaries | Select-Object name,overallPass,qualityGainCases,distanceGainKm,runtimeReductionMs,lossCases,lateRegressionCount,dominanceFailureCount | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $out.overallPass -and $out.verdict -ne "ADAPTIVE_ML_RUNTIME_GAIN_ONLY") { exit 1 }



