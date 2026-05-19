param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/final",
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }

& (Join-Path $PSScriptRoot "run-live-state-engine-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-state-engine" -SkipCompile
& (Join-Path $PSScriptRoot "run-dynamic-ml-dispatch-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-ml-dispatch" -SkipCompile
& (Join-Path $PSScriptRoot "run-live-api-contract-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-api-contract" -SkipCompile
& (Join-Path $PSScriptRoot "run-live-event-stream-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-event-stream" -SkipCompile
& (Join-Path $PSScriptRoot "run-dynamic-6case-benchmark.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-6case-benchmark" -SkipCompile
& (Join-Path $PSScriptRoot "run-dynamic-stress-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-stress" -SkipCompile
& (Join-Path $PSScriptRoot "run-dynamic-security-idempotency-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/security-idempotency" -SkipCompile
& (Join-Path $PSScriptRoot "run-dynamic-artifact-gate.ps1") -BaseUrl $BaseUrl -OutputDir "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/artifact-evidence" -SkipCompile

$state = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-state-engine/live-state-engine-summary.json") -Raw | ConvertFrom-Json
$dynamic = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-ml-dispatch/dynamic-ml-dispatch-summary.json") -Raw | ConvertFrom-Json
$api = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-api-contract/live-api-contract-summary.json") -Raw | ConvertFrom-Json
$events = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-event-stream/live-event-stream-summary.json") -Raw | ConvertFrom-Json
$bench = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-6case-benchmark/dynamic-6case-summary.json") -Raw | ConvertFrom-Json
$stress = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-stress/dynamic-stress-summary.json") -Raw | ConvertFrom-Json
$security = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/security-idempotency/security-idempotency-summary.json") -Raw | ConvertFrom-Json
$artifact = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/artifact-evidence/dynamic-artifact-summary.json") -Raw | ConvertFrom-Json

$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="v0.9.11-final"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  certificationScope="BACKEND_DYNAMIC_ML_DISPATCH_FINAL"
  liveStateEnginePass=[bool]$state.overallPass
  dynamicDispatchPass=[bool]$dynamic.overallPass
  forecastLivePass=([int]$dynamic.forecastOutputUsed -gt 0)
  greedRlLivePass=([int]$dynamic.greedRlActionUsed -gt 0)
  triModelRepairPass=([int]$dynamic.triModelRepairUsed -gt 0)
  apiContractPass=[bool]$api.overallPass
  eventStreamPass=[bool]$events.overallPass
  dynamic6CaseBenchmarkPass=[bool]$bench.overallPass
  stressPass=[bool]$stress.overallPass
  securityIdempotencyPass=[bool]$security.overallPass
  artifactEvidencePass=[bool]$artifact.overallPass
  dynamicBenchmarkPass=[bool]$bench.overallPass
  dashboardPlaygroundPass="DEFERRED_BY_SCOPE"
  fullReleaseReady=$false
  pendingGates=@()
  staleBufferedOrders=[int]$dynamic.staleBufferedOrders
  frozenStopViolations=([int]$dynamic.frozenStopViolations + [int]$bench.frozenStopViolations + [int]$stress.frozenStopViolations)
  pickupDropoffViolations=([int]$dynamic.pickupDropoffViolations + [int]$bench.pickupDropoffViolations + [int]$stress.pickupDropoffViolations)
  capacityViolations=([int]$dynamic.capacityViolations + [int]$bench.capacityViolations + [int]$stress.capacityViolations)
  lateRegression=([int]$dynamic.lateRegression + [int]$bench.lateRegression)
  coverageRegression=[int]$bench.coverageRegression
  dominanceFailures=([int]$dynamic.dominanceFailures + [int]$bench.dominanceFailures)
  safetyRegression=0
  overallPass=$false
}
$summary.safetyRegression = $summary.staleBufferedOrders + $summary.frozenStopViolations + $summary.pickupDropoffViolations + $summary.capacityViolations + $summary.lateRegression + $summary.coverageRegression + $summary.dominanceFailures
$summary.overallPass = $summary.liveStateEnginePass -and $summary.dynamicDispatchPass -and $summary.forecastLivePass -and $summary.greedRlLivePass -and $summary.triModelRepairPass -and $summary.apiContractPass -and $summary.eventStreamPass -and $summary.dynamic6CaseBenchmarkPass -and $summary.stressPass -and $summary.securityIdempotencyPass -and $summary.artifactEvidencePass -and $summary.safetyRegression -eq 0
$summary.fullReleaseReady = $summary.overallPass
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "final-summary.json")
if(-not $summary.overallPass) { throw "v0.9.11 dynamic ML dispatch final gate FAIL" }
Write-Host "[V0.9.11] PASS summary=$(Join-Path $out 'final-summary.json')"
