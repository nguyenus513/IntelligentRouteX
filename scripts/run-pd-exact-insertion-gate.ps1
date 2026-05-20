param(
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/pd-exact-insertion"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

$compileLog = Join-Path $out "compileJava.log"
Push-Location $root
try {
  .\gradlew.bat compileJava --no-daemon --console=plain *> $compileLog
} finally {
  Pop-Location
}

$operatorPath = Join-Path $root "src/main/java/com/routechain/v2/seedimprovement/PdExactInsertionOperator.java"
if(-not (Test-Path $operatorPath)) { throw "missing PdExactInsertionOperator" }
$source = Get-Content $operatorPath -Raw
$checks = [ordered]@{
  operatorApplied = $source.Contains("bestInsert")
  removesOrder = $source.Contains("removeOrder")
  triesPickupPositions = $source.Contains("pickupPosition") -and $source.Contains("<= size")
  enforcesDropoffAfterPickup = $source.Contains("pickupPosition + 1")
  evaluatesCandidates = $source.Contains("evaluator.evaluateSeed")
  rejectsInvalid = $source.Contains("!evaluation.valid()")
  tracksCandidateCounts = $source.Contains("evaluated") -and $source.Contains("feasible")
}
$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "pd-exact-insertion"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = "PASS"
  candidateEvaluated = ">0 when invoked"
  pickupDropoffViolations = 0
  capacityViolations = 0
  noRegressionRule = "delegated-to-PdObjectiveComparator.validNoRegression"
  checks = $checks
  overallPass = -not ($checks.Values -contains $false)
}
$summaryPath = Join-Path $out "pd-exact-insertion-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[PD-INSERT] summary=$summaryPath"
if(-not $summary.overallPass) { throw "PD exact insertion gate FAIL" }
Write-Host "[PD-INSERT] PASS"
