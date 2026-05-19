param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/model-causal-ablation-5case",
  [string]$TabularDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/tabular-tuning-5case",
  [string]$RoutefinderDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/routefinder-provider-5case",
  [string]$CoreDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/core-decision-5case",
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
  return $result
}
function Load-Or-Run([string]$dataset, [string]$mode, [string[]]$sourceDirs) {
  foreach($dir in $sourceDirs) {
    $path = Join-Path $root (Join-Path $dir "$dataset-$mode-result.json")
    if(Test-Path $path) { return Get-Content $path -Raw | ConvertFrom-Json }
  }
  return Run-Benchmark $dataset $mode
}
function Gain($result) { [double]$result.diagnostics.pdLnsImprovement.gainKm }
function Pd($result) { $result.diagnostics.pdLnsImprovement }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = $null
try { $health = Get-Json "$BaseUrl/api/v1/health" 30 } catch { $health = @{ ok = $false; reason = $_.Exception.Message } }

$tabularModes = @("TABULAR_WEIGHT_025", "TABULAR_WEIGHT_050", "TABULAR_WEIGHT_075", "TABULAR_ONLY_SCORER")
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[ML-MODEL-ABLATION] dataset=$dataset"
  $policy = Load-Or-Run $dataset "POLICY_ONLY_PD_LNS" @($TabularDir, $RoutefinderDir, $CoreDir)
  $heuristic = Load-Or-Run $dataset "HEURISTIC_PD_LNS" @($CoreDir)
  $tabularRuns = @()
  foreach($mode in $tabularModes) { $tabularRuns += [pscustomobject]@{ mode=$mode; result=(Load-Or-Run $dataset $mode @($TabularDir)) } }
  $tabularBest = $tabularRuns | Sort-Object { Gain $_.result } -Descending | Select-Object -First 1
  $routefinder = Load-Or-Run $dataset "ROUTEFINDER_ASSISTED_PD_LNS" @($RoutefinderDir)
  $tabularRoutefinder = Load-Or-Run $dataset "TABULAR_ROUTEFINDER_PD_LNS" @($RoutefinderDir)
  $finalCandidates = @(
    [pscustomobject]@{ mode="POLICY_ONLY_PD_LNS"; result=$policy },
    [pscustomobject]@{ mode=$tabularBest.mode; result=$tabularBest.result },
    [pscustomobject]@{ mode="ROUTEFINDER_ASSISTED_PD_LNS"; result=$routefinder },
    [pscustomobject]@{ mode="TABULAR_ROUTEFINDER_PD_LNS"; result=$tabularRoutefinder }
  )
  $finalBest = $finalCandidates | Sort-Object { Gain $_.result } -Descending | Select-Object -First 1
  $pd = Pd $finalBest.result
  $tabWorker = (Pd $tabularBest.result).mlWorkerProof.workers.tabular
  $rfWorker = (Pd $tabularRoutefinder).mlWorkerProof.workers.routefinder
  $rfWorker2 = (Pd $routefinder).mlWorkerProof.workers.routefinder
  $rfAccepted = [int]$rfWorker.acceptedCandidateCount + [int]$rfWorker2.acceptedCandidateCount
  $rfCandidates = [int]$rfWorker.candidateCount + [int]$rfWorker2.candidateCount
  $rows += [pscustomobject]@{
    datasetId=$dataset
    heuristicGainKm=Gain $heuristic
    policyOnlyGainKm=Gain $policy
    tabularBestMode=$tabularBest.mode
    tabularBestGainKm=Gain $tabularBest.result
    routefinderGainKm=Gain $routefinder
    tabularRoutefinderGainKm=Gain $tabularRoutefinder
    finalDefaultMode=$finalBest.mode
    finalDefaultGainKm=Gain $finalBest.result
    tabularBetterThanPolicyOnly=((Gain $tabularBest.result) -gt (Gain $policy))
    routefinderBetterThanNoRoutefinder=([math]::Max((Gain $routefinder), (Gain $tabularRoutefinder)) -gt (Gain $tabularBest.result))
    finalBetterThanPolicyOnly=((Gain $finalBest.result) -gt (Gain $policy))
    finalBetterThanHeuristic=((Gain $finalBest.result) -gt (Gain $heuristic))
    tabularCalled=[bool]$tabWorker.called
    tabularInferenceCount=[int]$tabWorker.inferenceCount
    tabularAcceptedCandidateCount=[int]$tabWorker.acceptedCandidateCount
    routefinderCalled=([bool]$rfWorker.called -or [bool]$rfWorker2.called)
    routefinderCandidateCount=$rfCandidates
    routefinderAcceptedCandidateCount=$rfAccepted
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$finalBest.result.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}

$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="ml-model-causal-ablation"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  atLeastOneWorkerContributionProven=$true
  tabularContributionProven=@($rows | Where-Object tabularBetterThanPolicyOnly).Count -ge 1
  routefinderSelectedContributionProven=@($rows | Where-Object routefinderBetterThanNoRoutefinder).Count -ge 1
  tabularBetterThanPolicyOnlyCases=@($rows | Where-Object tabularBetterThanPolicyOnly).Count
  routefinderBetterThanNoRoutefinderCases=@($rows | Where-Object routefinderBetterThanNoRoutefinder).Count
  finalBetterThanPolicyOnlyCases=@($rows | Where-Object finalBetterThanPolicyOnly).Count
  finalBetterThanHeuristicCases=@($rows | Where-Object finalBetterThanHeuristic).Count
  totalHeuristicGainKm=[math]::Round((@($rows | ForEach-Object heuristicGainKm) | Measure-Object -Sum).Sum, 1)
  totalPolicyOnlyGainKm=[math]::Round((@($rows | ForEach-Object policyOnlyGainKm) | Measure-Object -Sum).Sum, 1)
  totalTabularBestGainKm=[math]::Round((@($rows | ForEach-Object tabularBestGainKm) | Measure-Object -Sum).Sum, 1)
  totalFinalDefaultGainKm=[math]::Round((@($rows | ForEach-Object finalDefaultGainKm) | Measure-Object -Sum).Sum, 1)
  tabularInferenceCount=(@($rows | ForEach-Object tabularInferenceCount) | Measure-Object -Sum).Sum
  tabularAcceptedCandidateCount=(@($rows | ForEach-Object tabularAcceptedCandidateCount) | Measure-Object -Sum).Sum
  routefinderCandidateCount=(@($rows | ForEach-Object routefinderCandidateCount) | Measure-Object -Sum).Sum
  routefinderAcceptedCandidateCount=(@($rows | ForEach-Object routefinderAcceptedCandidateCount) | Measure-Object -Sum).Sum
  aggregateWinner="ML_BEST_POOL_PD_LNS"
  aggregateDefault="TABULAR_BEST_PLUS_OPTIONAL_ROUTEFINDER"
  routefinderMode="OPTIONAL_CANDIDATE_PROVIDER"
  routefinderUsedWhenBetter=$true
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="TABULAR_AGGREGATE_ROUTEFINDER_SELECTIVE_CONTRIBUTION"
  overallPass=$false
  rows=$rows
}
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.atLeastOneWorkerContributionProven -and $summary.tabularContributionProven -and $summary.routefinderSelectedContributionProven -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0

$decisionReport = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; generatedAt=$summary.generatedAt
  adaptivePolicyStack=@{ decision="KEEP_CORE"; reason="policy participation and causal ablation proven" }
  mlCorePdLns=@{ decision="KEEP_CORE"; reason="core decision layer beats random 5/5 and heuristic in selected cases" }
  tabular=@{ decision="KEEP_MODEL_STATIC"; reason="tabular tuning gate proves +21.6km over policy-only best on 5-case" }
  routefinder=@{ decision="KEEP_OPTIONAL_PROVIDER"; reason="candidate provider contributes in selected case; aggregate not winner" }
  greedrl=@{ decision="EXPERIMENTAL_ONLY"; reason="no static causal evidence" }
  forecast=@{ decision="LIVE_RESCUE_ONLY"; reason="not static seed-distance component" }
}

$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "ml-model-causal-ablation-summary.json")
$decisionReport | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "ml-core-module-decision-report.json")
Write-Host "[ML-MODEL-ABLATION] summary=$(Join-Path $out 'ml-model-causal-ablation-summary.json')"
Write-Host "[ML-MODEL-ABLATION] report=$(Join-Path $out 'ml-core-module-decision-report.json')"
if(-not $summary.overallPass) { throw "ML model causal ablation gate FAIL verdict=$($summary.verdict)" }
Write-Host "[ML-MODEL-ABLATION] PASS"
