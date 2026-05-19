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

$state = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-state-engine/live-state-engine-summary.json") -Raw | ConvertFrom-Json
$dynamic = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-ml-dispatch/dynamic-ml-dispatch-summary.json") -Raw | ConvertFrom-Json
$api = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-api-contract/live-api-contract-summary.json") -Raw | ConvertFrom-Json
$events = Get-Content (Join-Path $root "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/live-event-stream/live-event-stream-summary.json") -Raw | ConvertFrom-Json

$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="v0.9.11-final"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  certificationScope="CORE_LIVE_API_DISPATCH"
  liveStatePass=[bool]$state.overallPass
  dynamicDispatchPass=[bool]$dynamic.overallPass
  forecastLivePass=([int]$dynamic.forecastOutputUsed -gt 0)
  greedRlLivePass=([int]$dynamic.greedRlActionUsed -gt 0)
  triModelRepairPass=([int]$dynamic.triModelRepairUsed -gt 0)
  apiContractPass=[bool]$api.overallPass
  eventStreamPass=[bool]$events.overallPass
  dashboardPlaygroundPass=$false
  dynamicBenchmarkPass=$false
  fullReleaseReady=$false
  pendingGates=@("dashboard-live-playground", "dynamic-6case-benchmark")
  staleBufferedOrders=[int]$dynamic.staleBufferedOrders
  frozenStopViolations=[int]$dynamic.frozenStopViolations
  pickupDropoffViolations=[int]$dynamic.pickupDropoffViolations
  capacityViolations=[int]$dynamic.capacityViolations
  lateRegression=[int]$dynamic.lateRegression
  dominanceFailures=[int]$dynamic.dominanceFailures
  overallPass=$false
}
$summary.overallPass = $summary.liveStatePass -and $summary.dynamicDispatchPass -and $summary.forecastLivePass -and $summary.greedRlLivePass -and $summary.triModelRepairPass -and $summary.apiContractPass -and $summary.eventStreamPass -and $summary.staleBufferedOrders -eq 0 -and $summary.frozenStopViolations -eq 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "final-summary.json")
if(-not $summary.overallPass) { throw "v0.9.11 dynamic ML dispatch final gate FAIL" }
Write-Host "[V0.9.11] PASS summary=$(Join-Path $out 'final-summary.json')"
