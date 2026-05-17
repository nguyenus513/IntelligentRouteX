param(
  [Alias("InputDir")][string]$EvidenceDir = "artifacts/test-reports/ml-evidence",
  [string]$Output = "artifacts/test-reports/ml-evidence/loop-failure-analysis.json"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent) | Out-Null

function Latest($filter) {
  return Get-ChildItem -Path $EvidenceDir -Recurse -Filter $filter -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Read($filter) {
  $file = Latest $filter
  if ($null -eq $file) { return $null }
  return Get-Content $file.FullName -Raw | ConvertFrom-Json
}

$guided = Read "ml-guided-improvement-summary.json"
$ablation = Read "ml-ablation-restart-summary.json"
$evidence = Read "ml-evidence-gate-summary.json"
$decision = Read "ml-evidence-summary.json"

$failureType = "NONE"
$rootCause = "all known gates pass or no failure artifacts found"
$recommendation = "continue broader QUALITY/live/risk validation"

if ($null -eq $evidence -or $null -eq $decision) {
  $failureType = "ML_NOT_INSTRUMENTED"
  $rootCause = "mlEvidence or mlEvidenceSummary missing"
  $recommendation = "run scripts/run-ml-evidence-gate.ps1 and scripts/run-ml-decision-summary.ps1"
} elseif ($ablation -and $ablation.rows) {
  $full = $ablation.rows | Where-Object mode -eq "FULL_ML" | Select-Object -First 1
  $noAll = $ablation.rows | Where-Object mode -eq "NO_ML_ALL" | Select-Object -First 1
  if ($full -and $noAll -and [double]$full.distanceKm -eq [double]$noAll.distanceKm -and [int]$full.lateCount -eq [int]$noAll.lateCount -and [int64]$noAll.runtimeMs -lt [int64]$full.runtimeMs) {
    $failureType = "ML_NO_GAIN"
    $rootCause = "NO_ML_ALL equals FULL_ML on distance/late but is faster"
    $recommendation = "disable weak ML in static profile; keep RouteFinder/profile-only roles until broader datasets prove gain"
  }
}

if ($guided) {
  if (-not $guided.passChecks.coverageUnchanged) {
    $failureType = "COVERAGE_FAIL"
    $rootCause = "ML-guided result changes coverage vs best full seed"
    $recommendation = "fix coverage drain/repair before optimizing distance"
  } elseif (-not $guided.passChecks.lateNotWorse) {
    $failureType = "LATE_REGRESSION"
    $rootCause = "ML-guided result increases late count"
    $recommendation = "tighten schedule evaluator and acceptance rule"
  } elseif (-not $guided.passChecks.mlGuidedImprovesBestFullSeed) {
    $failureType = "BEST_SEED_NOT_IMPROVED"
    $rootCause = "ML-guided improver does not beat best full feasible seed"
    $recommendation = "improve RouteFinder exact evaluator, Tabular move ranker, GreedRL operator policy, or keep static optimization seed-driven"
  } elseif (-not $guided.passChecks.mlGuidedStrictGainVsHeuristic) {
    $failureType = "ML_NO_GAIN"
    $rootCause = "ML-guided improver is not strictly better than heuristic/no-ML improver"
    $recommendation = "prove ML on complex/risk datasets or prune ML from static hot path"
  }
}


$adaptiveQuality = @(Latest "adaptive-ml-quality-gain-summary.json"; Get-ChildItem -Path "artifacts/test-reports/adaptive-ml-policy" -Recurse -Filter "adaptive-ml-quality-gain-summary.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | Where-Object { $_ } | Select-Object -First 1
if ($adaptiveQuality) {
  $adaptive = Get-Content $adaptiveQuality.FullName -Raw | ConvertFrom-Json
  if ($adaptive.verdict -eq "ADAPTIVE_ML_QUALITY_GAIN_ACCEPTED" -or $adaptive.overallPass -eq $true) {
    $failureType = "ADAPTIVE_QUALITY_GAIN_PASS"
    $rootCause = "Adaptive ML quality seeking produced at least one distance/late quality gain with no guard regression"
    $recommendation = "v0.9.9 candidate passed; run broader QUALITY sanity before production tag if required"
  } elseif ($adaptive.verdict -eq "ADAPTIVE_ML_RUNTIME_GAIN_ONLY") {
    $failureType = "ADAPTIVE_RUNTIME_ONLY_GAIN"
    $rootCause = "Adaptive ML preserves quality and improves runtime/search, but has no distance/late quality gain"
    $recommendation = "keep v0.9.8 runtime-learning profile; increase quality budget only in benchmark/research profile"
  } elseif ($adaptive.verdict -eq "ADAPTIVE_ML_QUALITY_REGRESSION") {
    $failureType = "ADAPTIVE_QUALITY_REGRESSION"
    $rootCause = "Adaptive quality-gain run is worse than heuristic on distance/late/coverage or guard checks"
    $recommendation = "rollback adaptive state to v0.9.8 baseline, reduce exploration/adaptive weight, increase topK, keep dominance rollback"
  } elseif ($adaptive.guards.lateRegression -gt 0) {
    $failureType = "ADAPTIVE_LATE_REGRESSION"
    $rootCause = "Adaptive quality-gain run increased late count"
    $recommendation = "raise late/reject penalty and enforce late-not-worse invariant before reward update"
  } elseif ($adaptive.guards.dominanceFailures -gt 0) {
    $failureType = "ADAPTIVE_DOMINANCE_FAILURE"
    $rootCause = "Adaptive quality-gain run violated dominance guard"
    $recommendation = "force rollback to best seed and reduce adaptive pruning authority"
  } elseif ($adaptive.overallPass -ne $true -and $adaptive.qualityGain.improvedCases -eq 0) {
    $failureType = "ADAPTIVE_NO_QUALITY_GAIN"
    $rootCause = "Adaptive ML produced no distance/late improvement cases"
    $recommendation = "test complex/risk datasets or keep adaptive ML as runtime/search-efficiency layer only"
  }
}
$summary = [pscustomobject]@{
  schemaVersion = "loop-failure-analysis/v1"
  createdAt = (Get-Date).ToString("o")
  failureType = $failureType
  rootCause = $rootCause
  recommendation = $recommendation
  inputs = [pscustomobject]@{
    evidence = if (Latest "ml-evidence-gate-summary.json") { (Latest "ml-evidence-gate-summary.json").FullName } else { "MISSING" }
    ablation = if (Latest "ml-ablation-restart-summary.json") { (Latest "ml-ablation-restart-summary.json").FullName } else { "MISSING" }
    guidedImprovement = if (Latest "ml-guided-improvement-summary.json") { (Latest "ml-guided-improvement-summary.json").FullName } else { "MISSING" }
    decision = if (Latest "ml-evidence-summary.json") { (Latest "ml-evidence-summary.json").FullName } else { "MISSING" }
  }
}

$summary | ConvertTo-Json -Depth 10 | Set-Content $Output
Write-Output "SUMMARY=$Output"
if ($failureType -ne "NONE" -and $failureType -ne "ADAPTIVE_QUALITY_GAIN_PASS") { exit 1 }





