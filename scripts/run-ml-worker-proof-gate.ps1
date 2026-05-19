param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$Dataset = "raw-s",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-A-ml-participation-proof/worker",
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

$proof = $result.diagnostics.pdLnsImprovement.mlWorkerProof
$workers = $proof.workers
$calledWorkers = @($workers.PSObject.Properties | Where-Object { $_.Value.called })
$workersWithExplicitReason = @($workers.PSObject.Properties | Where-Object { -not $_.Value.called -and -not [string]::IsNullOrWhiteSpace([string]$_.Value.reason) })
$summary = [pscustomobject]@{
  version = "v0.9.10-A-ml-participation-proof"
  gate = "ml-worker-proof"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  datasetId = $Dataset
  jobId = $job.jobId
  blockPresent = [bool]$proof.blockPresent
  anyWorkerCalled = [bool]$proof.anyWorkerCalled
  workerContributionProven = [bool]$proof.workerContributionProven
  verdict = [string]$proof.verdict
  calledWorkerCount = $calledWorkers.Count
  disabledWorkerReasonCount = $workersWithExplicitReason.Count
  routefinder = $workers.routefinder
  tabular = $workers.tabular
  greedrl = $workers.greedrl
  forecast = $workers.forecast
  diagnosticPass = $false
  contributionPass = $false
}
$summary.diagnosticPass = $summary.blockPresent -and (($summary.calledWorkerCount -gt 0) -or ($summary.disabledWorkerReasonCount -eq 4))
$summary.contributionPass = $summary.workerContributionProven
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "ml-worker-proof-summary.json")
Write-Host "[ML-WORKER-PROOF] verdict=$($summary.verdict) diagnosticPass=$($summary.diagnosticPass) contributionPass=$($summary.contributionPass)"
if(-not $summary.diagnosticPass) { throw "ML worker proof diagnostic gate FAIL" }
Write-Host "[ML-WORKER-PROOF] PASS"
