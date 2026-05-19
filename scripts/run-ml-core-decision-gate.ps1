param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/core-decision-5case",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) { Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec $timeout }
function Run-Benchmark([string]$dataset, [string]$pdMode) {
  $path = Join-Path $out "$dataset-$pdMode-result.json"
  $request = @{ datasetId=$dataset; mode="QUALITY_BENCHMARK"; solvers=@("OR-Tools","PyVRP","VROOM","IntelligentRouteX"); adaptiveMlPolicyMode="QUALITY_SEEKING"; pdLnsMode=$pdMode; pdLnsMaxRounds=2; pdLnsTopBadOrders=8; pdLnsBudgetMs=3000 }
  $job = Post-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs" $request $TimeoutSec
  $result = $null; $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while((Get-Date) -lt $deadline) {
    try { $result = Get-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" 120; if($result.status -eq "COMPLETED" -or $result.runStatus -eq "COMPLETED" -or $result.status -eq "FAILED" -or $result.runStatus -eq "FAILED") { break } } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2
  }
  if($null -eq $result) { throw "timeout dataset=$dataset mode=$pdMode job=$($job.jobId)" }
  $result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
  return [pscustomobject]@{ jobId=$job.jobId; result=$result; path=$path }
}
function Gain($run) { [double]$run.result.diagnostics.pdLnsImprovement.gainKm }
function Pd($run) { $run.result.diagnostics.pdLnsImprovement }
function Proof($run) { $run.result.diagnostics.pdLnsImprovement.mlParticipationProof }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[ML-CORE] dataset=$dataset heuristic"; $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  Write-Host "[ML-CORE] dataset=$dataset policy"; $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  Write-Host "[ML-CORE] dataset=$dataset core"; $core = Run-Benchmark $dataset "ML_CORE_PD_LNS"
  Write-Host "[ML-CORE] dataset=$dataset random"; $random = Run-Benchmark $dataset "NO_ML_RANDOMIZED_PD_LNS"
  $pd = Pd $core; $proof = Proof $core; $worker = $pd.mlWorkerProof.workers.tabular
  $rows += [pscustomobject]@{
    datasetId=$dataset
    heuristicGainKm=Gain $heuristic
    policyOnlyGainKm=Gain $policy
    mlCoreGainKm=Gain $core
    randomizedGainKm=Gain $random
    mlCoreBetterThanHeuristic=((Gain $core) -gt (Gain $heuristic))
    mlCoreBetterThanPolicyOnly=((Gain $core) -gt (Gain $policy))
    mlCoreBetterThanRandom=((Gain $core) -gt (Gain $random))
    acceptedMlDecision=([int]$proof.acceptedMutationFromMlTopK -gt 0)
    decisionTraceCount=[int]$proof.decisionTraceCount
    mlRankedMutationCount=[int]$proof.rankedMutationCount
    acceptedMlRankedMutationCount=[int]$proof.acceptedMutationFromMlTopK
    tabularCalled=[bool]$worker.called
    tabularAffectedDecisionCount=[int]$worker.affectedDecisionCount
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$core.result.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}
$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="ml-core-decision"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  mlCoreAppliedCases=@($rows | Where-Object { $_.decisionTraceCount -gt 0 }).Count
  acceptedMlDecisionCases=@($rows | Where-Object acceptedMlDecision).Count
  mlCoreBetterThanHeuristicCases=@($rows | Where-Object mlCoreBetterThanHeuristic).Count
  mlCoreBetterThanPolicyOnlyCases=@($rows | Where-Object mlCoreBetterThanPolicyOnly).Count
  mlCoreBetterThanRandomCases=@($rows | Where-Object mlCoreBetterThanRandom).Count
  mlSelectedRouteCount=$rows.Count
  mlSelectedOrderCount=(@($rows | ForEach-Object decisionTraceCount) | Measure-Object -Sum).Sum
  mlSelectedOperatorCount=@($rows | Where-Object { $_.decisionTraceCount -gt 0 }).Count
  mlRankedMutationCount=(@($rows | ForEach-Object mlRankedMutationCount) | Measure-Object -Sum).Sum
  acceptedMlRankedMutationCount=(@($rows | ForEach-Object acceptedMlRankedMutationCount) | Measure-Object -Sum).Sum
  tabularCalledCases=@($rows | Where-Object tabularCalled).Count
  tabularAffectedDecisionCount=(@($rows | ForEach-Object tabularAffectedDecisionCount) | Measure-Object -Sum).Sum
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  overallPass=$false; rows=$rows
}
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.mlCoreAppliedCases -eq $summary.expected -and $summary.acceptedMlDecisionCases -ge 1 -and $summary.mlCoreBetterThanHeuristicCases -ge 1 -and $summary.mlCoreBetterThanRandomCases -ge 1 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "ml-core-decision-summary.json")
Write-Host "[ML-CORE] summary=$(Join-Path $out 'ml-core-decision-summary.json')"
if(-not $summary.overallPass) { throw "ML core decision gate FAIL" }
Write-Host "[ML-CORE] PASS"
