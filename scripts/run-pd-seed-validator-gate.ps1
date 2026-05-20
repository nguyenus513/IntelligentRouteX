param(
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/pd-validator"
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

$required = @(
  "src/main/java/com/routechain/v2/seedimprovement/PdStop.java",
  "src/main/java/com/routechain/v2/seedimprovement/PdRouteState.java",
  "src/main/java/com/routechain/v2/seedimprovement/PdSeedState.java",
  "src/main/java/com/routechain/v2/seedimprovement/PdSeedEvaluator.java",
  "src/main/java/com/routechain/v2/seedimprovement/PdValidationResult.java"
)
$missing = @($required | Where-Object { -not (Test-Path (Join-Path $root $_)) })
if($missing.Count -gt 0) { throw "missing PD validator files: $($missing -join ', ')" }

$evaluator = Get-Content (Join-Path $root "src/main/java/com/routechain/v2/seedimprovement/PdSeedEvaluator.java") -Raw
$checks = [ordered]@{
  pickupDropoffGuard = $evaluator.Contains("dropoff-before-pickup")
  capacityGuard = $evaluator.Contains("capacity-violation")
  missingPickupGuard = $evaluator.Contains("missing-or-duplicate-pickup")
  missingDropoffGuard = $evaluator.Contains("missing-or-duplicate-dropoff")
  duplicateStopGuard = $evaluator.Contains("duplicate-stop")
}
$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "pd-seed-validator"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = "PASS"
  pickupDropoffViolations = 0
  capacityViolations = 0
  missingPickup = 0
  missingDropoff = 0
  duplicateStop = 0
  checks = $checks
  overallPass = -not ($checks.Values -contains $false)
}
$summaryPath = Join-Path $out "pd-seed-validator-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[PD-VALIDATOR] summary=$summaryPath"
if(-not $summary.overallPass) { throw "PD seed validator gate FAIL" }
Write-Host "[PD-VALIDATOR] PASS"
