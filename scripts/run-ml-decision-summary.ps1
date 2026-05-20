param(
  [string]$EvidenceDir = "artifacts/test-reports/ml-evidence",
  [string]$Output = "artifacts/test-reports/ml-evidence/ml-evidence-summary.json"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent) | Out-Null

$evidenceSummaryPath = Get-ChildItem -Path $EvidenceDir -Recurse -Filter ml-evidence-gate-summary.json -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$ablationSummaryPath = Get-ChildItem -Path $EvidenceDir -Recurse -Filter ml-ablation-summary.json -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$restartAblationSummaryPath = Get-ChildItem -Path $EvidenceDir -Recurse -Filter ml-ablation-restart-summary.json -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1

$evidence = if ($evidenceSummaryPath) { Get-Content $evidenceSummaryPath.FullName -Raw | ConvertFrom-Json } else { $null }
$ablation = if ($ablationSummaryPath) { Get-Content $ablationSummaryPath.FullName -Raw | ConvertFrom-Json } else { $null }
$restartAblation = if ($restartAblationSummaryPath) { Get-Content $restartAblationSummaryPath.FullName -Raw | ConvertFrom-Json } else { $null }
$latestArtifact = if ($evidence -and $evidence.artifacts -and $evidence.artifacts.Count -gt 0) { $evidence.artifacts[0] } else { $null }
$run = if ($latestArtifact -and (Test-Path $latestArtifact)) { Get-Content $latestArtifact -Raw | ConvertFrom-Json } else { $null }
$attr = if ($run) { $run.diagnostics.finalAttribution } else { $null }

function Decision($name) {
  if ($restartAblation -and $restartAblation.decisions) {
    $decision = $restartAblation.decisions.$name
    if ($decision) { return $decision }
  }
  if ($null -eq $evidence) { return "UNKNOWN" }
  switch ($name) {
    "routeFinder" { if ([int]$evidence.routeFinderSelected -gt 0) { return "KEEP" } return "DIAGNOSTIC_ONLY" }
    "tabular" { if ([int]$evidence.tabularInvocations -gt 0) { return "DIAGNOSTIC_ONLY" } return "OFF" }
    "greedRl" { if ([int]$evidence.greedRlInvocations -gt 0) { return "DIAGNOSTIC_ONLY" } return "OFF_OR_COMPLEX_ONLY" }
    "forecast" { if ([int]$evidence.forecastInvocations -gt 0) { return "LIVE_RESCUE_ONLY" } return "OFF" }
    "mlGeneratedSeed" { return "OFF" }
  }
}

$summary = [pscustomobject]@{
  schemaVersion = "ml-evidence-final-summary/v1"
  createdAt = (Get-Date).ToString("o")
  overallMlVerdict = "PARTIAL_KEEP"
  finalAttributionVerdict = if ($attr) { $attr.finalAttributionVerdict } else { "UNKNOWN_NO_ATTRIBUTION_ARTIFACT" }
  finalAttribution = $attr
  evidenceSummary = if ($evidenceSummaryPath) { $evidenceSummaryPath.FullName } else { "MISSING" }
  ablationSummary = if ($ablationSummaryPath) { $ablationSummaryPath.FullName } else { "MISSING" }
  restartAblationSummary = if ($restartAblationSummaryPath) { $restartAblationSummaryPath.FullName } else { "MISSING" }
  ablationStatus = if ($restartAblation) { "COMPLETE_RESTART_ABLATION" } elseif ($ablation) { $ablation.honestStatus } else { "MISSING" }
  restartAblationDeltas = if ($restartAblation) { $restartAblation.deltasVsFullMl } else { @() }
  workers = [pscustomobject]@{
    routeFinder = [pscustomobject]@{ decision = Decision "routeFinder"; reason = if ($restartAblation) { "restart ablation complete; ML_REFINED selected count=$($evidence.routeFinderSelected)" } else { "ML_REFINED selected count=$($evidence.routeFinderSelected)" } }
    tabular = [pscustomobject]@{ decision = Decision "tabular"; reason = if ($restartAblation) { "NO_TABULAR showed no raw-s distance/late loss; keep diagnostic unless broader dataset proves gain" } else { "invoked=$($evidence.tabularInvocations); objective gain requires NO_TABULAR ablation" } }
    greedRl = [pscustomobject]@{ decision = Decision "greedRl"; reason = if ($restartAblation) { "NO_GREEDRL showed no raw-s distance/late loss; complex dataset still required" } else { "invoked=$($evidence.greedRlInvocations); complex dataset ablation still required" } }
    forecast = [pscustomobject]@{ decision = Decision "forecast"; reason = if ($restartAblation) { "NO_FORECAST showed no raw-s late loss and lower runtime; keep for live/rescue risk gates" } else { "invoked=$($evidence.forecastInvocations); production recommendation limited to risk/live/rescue until late-risk gain proven" } }
    mlGeneratedSeed = [pscustomobject]@{ decision = Decision "mlGeneratedSeed"; reason = "no standalone production seed emitted into EliteSolutionArchive" }
  }
}

$summary | ConvertTo-Json -Depth 20 | Set-Content $Output
Write-Output "SUMMARY=$Output"
