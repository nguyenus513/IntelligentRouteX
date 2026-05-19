param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$Dataset = "raw-s",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-A-ml-participation-proof/participation",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 600
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) {
  Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec $timeout
}

if(-not $SkipCompile) {
  Push-Location $root
  try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location }
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$request = @{
  datasetId = $Dataset
  mode = "QUALITY_BENCHMARK"
  solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
  adaptiveMlPolicyMode = "QUALITY_SEEKING"
  pdLnsMode = "ML_HYBRID_PD_LNS"
  pdLnsMaxRounds = 2
  pdLnsTopBadOrders = 8
  pdLnsBudgetMs = 3000
}
$job = Post-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs" $request $TimeoutSec
$result = $null
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while((Get-Date) -lt $deadline) {
  try {
    $result = Get-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" 120
    if($result.status -eq "COMPLETED" -or $result.runStatus -eq "COMPLETED") { break }
    if($result.status -eq "FAILED" -or $result.runStatus -eq "FAILED") { break }
  } catch { Start-Sleep -Seconds 2 }
  Start-Sleep -Seconds 2
}
if($null -eq $result) { throw "timeout dataset=$Dataset job=$($job.jobId)" }
$resultPath = Join-Path $out "$Dataset-ML_HYBRID_PD_LNS-result.json"
$result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $resultPath

$proof = $result.diagnostics.pdLnsImprovement.mlParticipationProof
$policy = $proof.policyLayer
$summary = [pscustomobject]@{
  version = "v0.9.10-A-ml-participation-proof"
  gate = "ml-participation-proof"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  datasetId = $Dataset
  jobId = $job.jobId
  decisionTraceCount = [int]$proof.decisionTraceCount
  rankedMutationCount = [int]$proof.rankedMutationCount
  acceptedMutationFromMlTopK = [int]$proof.acceptedMutationFromMlTopK
  rewardUpdates = [int]$proof.rewardUpdates
  adaptiveSeedPolicyUsed = [bool]$policy.adaptiveSeedPolicy.used
  adaptiveOperatorPolicyUsed = [bool]$policy.adaptiveOperatorPolicy.used
  adaptiveMovePriorityUsed = [bool]$policy.adaptiveMovePriority.used
  adaptiveRewardCalculatorUsed = [bool]$policy.adaptiveRewardCalculator.used
  pickupDropoffViolations = [int]$result.diagnostics.pdLnsImprovement.pickupDropoffViolations
  capacityViolations = [int]$result.diagnostics.pdLnsImprovement.capacityViolations
  lateRegression = [int]$result.diagnostics.pdLnsImprovement.lateRegression
  coverageRegression = [int]$result.diagnostics.pdLnsImprovement.coverageRegression
  overallPass = $false
}
$summary.overallPass = $summary.decisionTraceCount -gt 0 `
  -and $summary.rankedMutationCount -gt 0 `
  -and $summary.acceptedMutationFromMlTopK -gt 0 `
  -and $summary.rewardUpdates -gt 0 `
  -and $summary.adaptiveSeedPolicyUsed `
  -and $summary.adaptiveOperatorPolicyUsed `
  -and $summary.adaptiveMovePriorityUsed `
  -and $summary.adaptiveRewardCalculatorUsed `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0
$summaryPath = Join-Path $out "ml-participation-proof-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[ML-PARTICIPATION-PROOF] summary=$summaryPath"
if(-not $summary.overallPass) { throw "ML participation proof gate FAIL" }
Write-Host "[ML-PARTICIPATION-PROOF] PASS"
