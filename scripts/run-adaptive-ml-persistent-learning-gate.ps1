param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [int]$Rounds = 3,
  [string]$StatePath = "artifacts/adaptive-ml/adaptive-learning-state.json",
  [string]$OutputDir = "artifacts/test-reports/adaptive-ml-policy/v0.9.8-persistent-learning"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $StatePath -Parent) | Out-Null
Remove-Item $StatePath -ErrorAction SilentlyContinue

function ReadJson($path) {
  if (-not (Test-Path $path)) { return $null }
  return Get-Content $path -Raw | ConvertFrom-Json
}

$roundRows = @()
for ($round = 1; $round -le $Rounds; $round++) {
  $roundDir = Join-Path $OutputDir "round-$round"
  & scripts/run-adaptive-ml-policy-gate.ps1 `
    -BaseUrl $BaseUrl `
    -Datasets $Datasets `
    -Modes @("HEURISTIC_IMPROVER", "ADAPTIVE_ML_POLICY_TOP_K") `
    -PersistenceEnabled `
    -StatePath $StatePath `
    -OutputDir $roundDir | Out-Host
  $summary = ReadJson (Join-Path $roundDir "adaptive-ml-policy-summary.json")
  $final = ReadJson (Join-Path $roundDir "adaptive-ml-policy-final-summary.json")
  if ($null -eq $final -or $final.overallPass -ne $true) { throw "adaptive-policy-round-$round-failed" }
  $adaptiveRows = @($summary.rows | Where-Object { $_.mode -ne "HEURISTIC_IMPROVER" })
  $distanceTotal = ($adaptiveRows | Measure-Object -Property distanceKm -Sum).Sum
  $runtimeTotal = ($adaptiveRows | Measure-Object -Property runtimeMs -Sum).Sum
  $evaluatedMovesTotal = ($adaptiveRows | Measure-Object -Property evaluatedMoves -Sum).Sum
  $acceptedMovesTotal = ($adaptiveRows | Measure-Object -Property acceptedMoves -Sum).Sum
  $rewardTotal = ($adaptiveRows | Measure-Object -Property rewardTotal -Sum).Sum
  $scoredMovesTotal = ($adaptiveRows | Measure-Object -Property scoredMoves -Sum).Sum
  $roundRows += [pscustomobject]@{
    round = $round
    distanceKmTotal = [math]::Round([double]$distanceTotal, 3)
    runtimeMsTotal = [int64]$runtimeTotal
    evaluatedMovesTotal = [int]$evaluatedMovesTotal
    acceptedMovesTotal = [int]$acceptedMovesTotal
    acceptedMoveRate = [math]::Round([double]$acceptedMovesTotal / [math]::Max(1, [double]$scoredMovesTotal), 3)
    rewardTotal = [math]::Round([double]$rewardTotal, 3)
    lateRegressionCount = [int]$final.aggregate.lateRegressionCount
    dominanceFailureCount = [int]$final.aggregate.dominanceFailureCount
    lossCount = [int]$final.aggregate.lossCount
    noWorseCount = [int]$final.aggregate.noWorseCount
    gainCount = [int]$final.aggregate.gainCount
    moveOrderingAppliedCount = [int]$final.aggregate.moveOrderingAppliedCount
    topKAppliedCount = [int]$final.aggregate.topKAppliedCount
    summary = Join-Path $roundDir "adaptive-ml-policy-summary.json"
  }
}

$round1 = $roundRows | Where-Object round -eq 1 | Select-Object -First 1
$round3 = $roundRows | Where-Object round -eq ([math]::Min(3, $Rounds)) | Select-Object -First 1
$qualityNoWorse = $round3.distanceKmTotal -le $round1.distanceKmTotal -and $round3.lateRegressionCount -eq 0 -and $round3.dominanceFailureCount -eq 0 -and $round3.lossCount -eq 0
$runtimeReduction = [int64]$round1.runtimeMsTotal - [int64]$round3.runtimeMsTotal
$evaluatedMoveReduction = [int]$round1.evaluatedMovesTotal - [int]$round3.evaluatedMovesTotal
$acceptedMoveRateGain = [math]::Round([double]$round3.acceptedMoveRate - [double]$round1.acceptedMoveRate, 3)
$rewardGain = [math]::Round([double]$round3.rewardTotal - [double]$round1.rewardTotal, 3)
$distanceGainKm = [math]::Round([double]$round1.distanceKmTotal - [double]$round3.distanceKmTotal, 3)
$hasGain = $runtimeReduction -gt 0 -or $evaluatedMoveReduction -gt 0 -or $acceptedMoveRateGain -gt 0 -or $rewardGain -gt 0 -or $distanceGainKm -gt 0

$summaryOut = [pscustomobject]@{
  schemaVersion = "adaptive-ml-persistent-learning-summary/v1"
  createdAt = (Get-Date).ToString("o")
  overallPass = [bool]($qualityNoWorse -and $hasGain)
  verdict = if ($qualityNoWorse -and $hasGain) { "ADAPTIVE_ML_PERSISTENT_LEARNING_ACCEPTED" } elseif ($qualityNoWorse) { "ADAPTIVE_ML_PERSISTENT_LEARNING_NO_GAIN" } else { "ADAPTIVE_ML_PERSISTENT_LEARNING_REGRESSION" }
  statePath = $StatePath
  stateExists = Test-Path $StatePath
  rounds = $roundRows
  learningGain = [pscustomobject]@{
    runtimeReductionMs = $runtimeReduction
    evaluatedMoveReduction = $evaluatedMoveReduction
    acceptedMoveRateGain = $acceptedMoveRateGain
    rewardGain = $rewardGain
    distanceGainKm = $distanceGainKm
  }
}

$summaryPath = Join-Path $OutputDir "adaptive-ml-persistent-learning-summary.json"
$summaryOut | ConvertTo-Json -Depth 30 | Set-Content $summaryPath
$roundRows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summaryOut.overallPass) { exit 1 }
