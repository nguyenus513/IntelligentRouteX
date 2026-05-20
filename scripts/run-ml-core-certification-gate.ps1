param(
  [string]$BaseUrl = "http://localhost:18116",
  [int]$Port = 18116,
  [string]$OutputDir = "artifacts/test-reports/ml-core/certification",
  [string[]]$Datasets = @("raw-s"),
  [switch]$UseExistingArtifacts,
  [switch]$SkipBuild,
  [switch]$SkipQuality,
  [switch]$SkipLiveRescue
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function StepResult($name, $status, $artifact, $note) {
  return [pscustomobject]@{ name = $name; status = $status; artifact = $artifact; note = $note }
}

function Latest($root, $filter) {
  return Get-ChildItem -Path $root -Recurse -Filter $filter -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function ReadJson($path) {
  if ($null -eq $path -or -not (Test-Path $path)) { return $null }
  return Get-Content $path -Raw | ConvertFrom-Json
}

function RunStep($name, [scriptblock]$body) {
  try {
    return & $body
  } catch {
    return StepResult $name "FAIL" "" $_.Exception.Message
  }
}

$steps = @()

$steps += RunStep "compileJava" {
  if ($SkipBuild) { return StepResult "compileJava" "SKIPPED" "" "SkipBuild set" }
  $env:GRADLE_USER_HOME = (Resolve-Path '.').Path + '\.gradle-tmp'
  & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "compileJava failed exit=$LASTEXITCODE" }
  return StepResult "compileJava" "PASS" "" "BUILD SUCCESSFUL"
}
`r`n
$mlEvidenceDir = Join-Path $OutputDir "ml-evidence"
$mlAblationDir = Join-Path $OutputDir "ml-ablation-restart"
$mlGuidedDir = Join-Path $OutputDir "ml-guided-improvement"

$steps += RunStep "mlEvidence" {
  if ($UseExistingArtifacts) {
    $latest = Latest "artifacts/test-reports/ml-evidence" "ml-evidence-gate-summary.json"
    if ($latest) { return StepResult "mlEvidence" "PASS" $latest.FullName "reused existing evidence" }
    throw "missing existing ml-evidence-gate-summary.json"
  }
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-ml-evidence-gate.ps1 -BaseUrl $BaseUrl -Datasets $Datasets -OutputDir $mlEvidenceDir | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "ml evidence gate failed exit=$LASTEXITCODE" }
  $summary = Join-Path $mlEvidenceDir "ml-evidence-gate-summary.json"
  return StepResult "mlEvidence" "PASS" $summary "evidence gate PASS"
}

$steps += RunStep "mlAblationRestart" {
  if ($UseExistingArtifacts) {
    $latest = Latest "artifacts/test-reports/ml-evidence" "ml-ablation-restart-summary.json"
    if ($latest) { return StepResult "mlAblationRestart" "PASS" $latest.FullName "reused existing restart ablation" }
    throw "missing existing ml-ablation-restart-summary.json"
  }
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-ml-ablation-restart-loop.ps1 -BaseUrl $BaseUrl -Port $Port -Datasets $Datasets -OutputDir $mlAblationDir | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "ml ablation restart loop failed exit=$LASTEXITCODE" }
  $summary = Join-Path $mlAblationDir "ml-ablation-restart-summary.json"
  return StepResult "mlAblationRestart" "PASS" $summary "restart ablation PASS"
}

$steps += RunStep "mlDecisionSummary" {
  $evidenceRoot = if ($UseExistingArtifacts) { "artifacts/test-reports/ml-evidence" } else { $OutputDir }
  $out = Join-Path $OutputDir "ml-evidence-summary.json"
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-ml-decision-summary.ps1 -EvidenceDir $evidenceRoot -Output $out | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "ml decision summary failed exit=$LASTEXITCODE" }
  return StepResult "mlDecisionSummary" "PASS" $out "worker decisions written"
}

$steps += RunStep "mlGuidedImprovement" {
  $ablationRoot = if ($UseExistingArtifacts) { "artifacts/test-reports/ml-evidence/ablation-restart" } else { $mlAblationDir }
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-ml-guided-improvement-gate.ps1 -BaseUrl $BaseUrl -Datasets $Datasets -AblationDir $ablationRoot -OutputDir $mlGuidedDir | Out-Host
  $summary = Join-Path $mlGuidedDir "ml-guided-improvement-summary.json"
  if ($LASTEXITCODE -ne 0) { return StepResult "mlGuidedImprovement" "FAIL" $summary "strict ML-guided gate failed; inspect honestStatus" }
  return StepResult "mlGuidedImprovement" "PASS" $summary "ML-guided gate PASS"
}

$steps += RunStep "failureAnalysis" {
  $root = if ($UseExistingArtifacts) { "artifacts/test-reports/ml-evidence" } else { $OutputDir }
  & powershell.exe -ExecutionPolicy Bypass -File scripts/analyze-loop-failures.ps1 -EvidenceDir $root -Output (Join-Path $OutputDir "loop-failure-analysis.json") | Out-Host
  $summary = Join-Path $OutputDir "loop-failure-analysis.json"
  if ($LASTEXITCODE -ne 0) { return StepResult "failureAnalysis" "FAIL" $summary "classifier found actionable failure" }
  return StepResult "failureAnalysis" "PASS" $summary "no classifier failure"
}

$steps += RunStep "finalContributionReport" {
  $root = if ($UseExistingArtifacts) { "artifacts/test-reports/ml-evidence" } else { $OutputDir }
  $out = Join-Path $OutputDir "ml-final-contribution-report.json"
  & powershell.exe -ExecutionPolicy Bypass -File scripts/write-ml-final-contribution-report.ps1 -EvidenceDir $root -Output $out | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "final contribution report failed exit=$LASTEXITCODE" }
  return StepResult "finalContributionReport" "PASS" $out "final report written"
}

$steps += RunStep "qualitySanity" {
  if ($SkipQuality) { return StepResult "qualitySanity" "SKIPPED" "" "SkipQuality set" }
  $dir = Join-Path $OutputDir "quality"
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-quality-benchmark-gate.ps1 -BaseUrl $BaseUrl -OutputDir $dir | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "quality benchmark gate failed exit=$LASTEXITCODE" }
  return StepResult "qualitySanity" "PASS" $dir "QUALITY gate PASS"
}

$steps += RunStep "liveRescueRisk" {
  if ($SkipLiveRescue) { return StepResult "liveRescueRisk" "SKIPPED" "" "SkipLiveRescue set" }
  $liveDir = Join-Path $OutputDir "live-stress"
  $rescueDir = Join-Path $OutputDir "rescue"
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-live-stress-gate.ps1 -BaseUrl $BaseUrl -OutputDir $liveDir | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "live stress gate failed exit=$LASTEXITCODE" }
  & powershell.exe -ExecutionPolicy Bypass -File scripts/run-rescue-gate.ps1 -BaseUrl $BaseUrl -OutputDir $rescueDir | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "rescue gate failed exit=$LASTEXITCODE" }
  return StepResult "liveRescueRisk" "PASS" "$liveDir;$rescueDir" "live/rescue PASS"
}

$decision = ReadJson (Join-Path $OutputDir "ml-evidence-summary.json")
$guided = ReadJson (Join-Path $mlGuidedDir "ml-guided-improvement-summary.json")
$finalContribution = ReadJson (Join-Path $OutputDir "ml-final-contribution-report.json")
$hardFail = @($steps | Where-Object { $_.status -eq "FAIL" -and $_.name -notin @("mlGuidedImprovement", "failureAnalysis") }).Count -gt 0
$strictMlProven = $guided -and $guided.passChecks -and $guided.passChecks.mlGuidedStrictGainVsHeuristic
$allDecisionsPresent = $decision -and $decision.workers -and $decision.workers.routeFinder -and $decision.workers.tabular -and $decision.workers.greedRl -and $decision.workers.forecast -and $decision.workers.mlGeneratedSeed

$summary = [pscustomobject]@{
  schemaVersion = "ml-core-certification-gate/v1"
  createdAt = (Get-Date).ToString("o")
  overallPass = (-not $hardFail) -and $allDecisionsPresent
  mlCoreVerdict = if ($strictMlProven) { "CERTIFIED_STRICT_ML_GAIN" } elseif ($allDecisionsPresent -and -not $hardFail) { "CERTIFIED_SELECTIVE_KEEP_STATIC_ML_GAIN_NOT_PROVEN" } else { "NOT_CERTIFIED" }
  strictMlGainProven = [bool]$strictMlProven
  workers = if ($decision) { $decision.workers } else { $null }
  proposedArchitecture = [pscustomobject]@{
    staticDefault = [pscustomobject]@{ routeFinder = "ON"; tabular = "OFF_OR_DIAGNOSTIC"; greedRl = "OFF_OR_COMPLEX_ONLY"; forecast = "OFF"; mlGeneratedSeed = "OFF" }
    qualityResearch = [pscustomobject]@{ routeFinder = "ON"; learnedMoveRanker = "NEXT"; learnedOperatorPolicy = "NEXT"; forecastRiskOnly = "NEXT" }
    liveRescue = [pscustomobject]@{ routeFinder = "ON"; forecast = "ON_IF_RISK_GATE_PROVES"; greedRl = "COMPLEX_ONLY"; riskAwareEtaModel = "NEXT" }
  }
  guidedImprovement = $guided
  finalContribution = $finalContribution
  steps = $steps
}

$summaryPath = Join-Path $OutputDir "ml-core-final-summary.json"
$summary | ConvertTo-Json -Depth 40 | Set-Content $summaryPath
$steps | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.overallPass) { exit 1 }

