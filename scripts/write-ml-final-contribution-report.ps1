param(
  [string]$EvidenceDir = "artifacts/test-reports/ml-evidence",
  [string]$Output = "artifacts/test-reports/ml-evidence/ml-final-contribution-report.json"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent) | Out-Null

function Latest($filter) {
  return Get-ChildItem -Path $EvidenceDir -Recurse -Filter $filter -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function ReadLatest($filter) {
  $file = Latest $filter
  if ($null -eq $file) { return $null }
  return Get-Content $file.FullName -Raw | ConvertFrom-Json
}

$decision = ReadLatest "ml-evidence-summary.json"
$guided = ReadLatest "ml-guided-improvement-summary.json"
$failure = ReadLatest "loop-failure-analysis.json"
$ablation = ReadLatest "ml-ablation-restart-summary.json"

function Worker($name, $fallbackDecision, $fallbackEvidence) {
  $worker = if ($decision -and $decision.workers) { $decision.workers.$name } else { $null }
  return [pscustomobject]@{
    decision = if ($worker) { $worker.decision } else { $fallbackDecision }
    evidence = if ($worker) { $worker.reason } else { $fallbackEvidence }
  }
}

$qualitySource = if ($decision -and $decision.finalAttributionVerdict) { $decision.finalAttributionVerdict } else { "UNKNOWN" }
$baseline = if ($guided) {
  [pscustomobject]@{
    bestFullSeedSource = $guided.attribution.bestFullSeedSource
    mlGuidedFinalSource = $guided.attribution.mlGuidedFinalSource
    deltaMlVsBestSeedKm = $guided.attribution.deltaMlVsBestSeedKm
    lossVsBestSeed = if ($guided.passChecks.mlGuidedImprovesBestFullSeed -or $guided.passChecks.mlGuidedNotWorseThanHeuristic) { 0 } else { 1 }
    mlGuidedImprovementGate = if ($guided.pass) { "PASS" } else { "FAIL" }
  }
} else {
  [pscustomobject]@{ mlGuidedImprovementGate = "MISSING"; lossVsBestSeed = "UNKNOWN" }
}

$overallVerdict = if ($guided -and $guided.passChecks -and $guided.passChecks.mlGuidedStrictGainVsHeuristic) {
  "ML_GUIDED_IMPROVER_PROVEN"
} elseif ($guided -and $guided.pass) {
  "BEST_SEED_IMPROVED_ML_NOT_STRICTLY_PROVEN"
} elseif ($decision) {
  "ML_SELECTIVE_KEEP"
} else {
  "ML_EVIDENCE_INCOMPLETE"
}

$summary = [pscustomobject]@{
  schemaVersion = "ml-final-contribution-report/v1"
  createdAt = (Get-Date).ToString("o")
  overallVerdict = $overallVerdict
  qualitySource = $qualitySource
  mlContribution = [pscustomobject]@{
    routeFinder = Worker "routeFinder" "UNKNOWN" "decision summary missing"
    tabular = Worker "tabular" "UNKNOWN" "decision summary missing"
    greedRl = Worker "greedRl" "UNKNOWN" "decision summary missing"
    forecast = Worker "forecast" "UNKNOWN" "decision summary missing"
    mlGeneratedSeed = Worker "mlGeneratedSeed" "OFF" "no standalone seed emitted"
  }
  guidedImprovement = if ($guided) { $guided } else { "MISSING" }
  baselinePerformance = $baseline
  failureAnalysis = if ($failure) { $failure } else { "MISSING" }
  ablationSummary = if ($ablation) { [pscustomobject]@{ decisions = $ablation.decisions; deltasVsFullMl = $ablation.deltasVsFullMl } } else { "MISSING" }
  sourceFiles = [pscustomobject]@{
    decisionSummary = if (Latest "ml-evidence-summary.json") { (Latest "ml-evidence-summary.json").FullName } else { "MISSING" }
    guidedImprovement = if (Latest "ml-guided-improvement-summary.json") { (Latest "ml-guided-improvement-summary.json").FullName } else { "MISSING" }
    failureAnalysis = if (Latest "loop-failure-analysis.json") { (Latest "loop-failure-analysis.json").FullName } else { "MISSING" }
    ablation = if (Latest "ml-ablation-restart-summary.json") { (Latest "ml-ablation-restart-summary.json").FullName } else { "MISSING" }
  }
}

$summary | ConvertTo-Json -Depth 30 | Set-Content $Output
Write-Output "SUMMARY=$Output"
