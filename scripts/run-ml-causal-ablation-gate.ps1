param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-A-ml-participation-proof/causal-ablation",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) {
  Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec $timeout
}

function Run-Benchmark([string]$dataset, [string]$pdMode) {
  $safeMode = $pdMode.Replace(':','_')
  $path = Join-Path $out "$dataset-$safeMode-result.json"
  $request = @{
    datasetId = $dataset
    mode = "QUALITY_BENCHMARK"
    solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
    adaptiveMlPolicyMode = "QUALITY_SEEKING"
    pdLnsMode = $pdMode
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
  if($null -eq $result) { throw "timeout dataset=$dataset mode=$pdMode job=$($job.jobId)" }
  $result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
  return [pscustomobject]@{ jobId = $job.jobId; result = $result; path = $path }
}

function Gain($run) { [double]$run.result.diagnostics.pdLnsImprovement.gainKm }
function Pd($run) { $run.result.diagnostics.pdLnsImprovement }
function Proof($run) { $run.result.diagnostics.pdLnsImprovement.mlParticipationProof }
function DominancePassed($run) { [bool]$run.result.diagnostics.baselineDominanceGuard.baselineDominancePassed }

if(-not $SkipCompile) {
  $compileLog = Join-Path $out "compileJava.log"
  Push-Location $root
  try { .\gradlew.bat compileJava --no-daemon --console=plain *> $compileLog } finally { Pop-Location }
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset heuristic"
  $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset full"
  $full = Run-Benchmark $dataset "FULL_ML_PD_LNS"
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset no-policy"
  $noPolicy = Run-Benchmark $dataset "NO_ADAPTIVE_POLICY"
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset no-move-priority"
  $noMove = Run-Benchmark $dataset "NO_ADAPTIVE_MOVE_PRIORITY"
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset no-operator-policy"
  $noOperator = Run-Benchmark $dataset "NO_ADAPTIVE_OPERATOR_POLICY"
  Write-Host "[ML-CAUSAL-ABLATION] dataset=$dataset no-reward"
  $noReward = Run-Benchmark $dataset "NO_REWARD_UPDATE"

  $fullGain = Gain $full
  $noPolicyGain = Gain $noPolicy
  $noMoveGain = Gain $noMove
  $noOperatorGain = Gain $noOperator
  $noRewardGain = Gain $noReward
  $heuristicGain = Gain $heuristic
  $pd = Pd $full
  $proof = Proof $full
  $rows += [pscustomobject]@{
    datasetId = $dataset
    heuristicJobId = $heuristic.jobId
    fullJobId = $full.jobId
    noAdaptivePolicyJobId = $noPolicy.jobId
    noMovePriorityJobId = $noMove.jobId
    noOperatorPolicyJobId = $noOperator.jobId
    noRewardUpdateJobId = $noReward.jobId
    heuristicGainKm = $heuristicGain
    fullMlGainKm = $fullGain
    noAdaptivePolicyGainKm = $noPolicyGain
    noMovePriorityGainKm = $noMoveGain
    noOperatorPolicyGainKm = $noOperatorGain
    noRewardUpdateGainKm = $noRewardGain
    fullBetterThanHeuristic = $fullGain -gt $heuristicGain
    fullBetterThanNoAdaptivePolicy = $fullGain -gt $noPolicyGain
    fullBetterThanNoMovePriority = $fullGain -gt $noMoveGain
    fullBetterThanNoOperatorPolicy = $fullGain -gt $noOperatorGain
    fullBetterThanNoRewardUpdate = $fullGain -gt $noRewardGain
    acceptedMutationFromMlTopK = [int]$proof.acceptedMutationFromMlTopK
    rewardUpdates = [int]$proof.rewardUpdates
    pickupDropoffViolations = [int]$pd.pickupDropoffViolations
    capacityViolations = [int]$pd.capacityViolations
    lateRegression = [int]$pd.lateRegression
    coverageRegression = [int]$pd.coverageRegression
    dominancePassed = DominancePassed $full
  }
}

$totalFull = [math]::Round((@($rows | ForEach-Object { [double]$_.fullMlGainKm }) | Measure-Object -Sum).Sum, 1)
$totalHeuristic = [math]::Round((@($rows | ForEach-Object { [double]$_.heuristicGainKm }) | Measure-Object -Sum).Sum, 1)
$totalNoPolicy = [math]::Round((@($rows | ForEach-Object { [double]$_.noAdaptivePolicyGainKm }) | Measure-Object -Sum).Sum, 1)
$totalNoMove = [math]::Round((@($rows | ForEach-Object { [double]$_.noMovePriorityGainKm }) | Measure-Object -Sum).Sum, 1)
$totalNoOperator = [math]::Round((@($rows | ForEach-Object { [double]$_.noOperatorPolicyGainKm }) | Measure-Object -Sum).Sum, 1)
$totalNoReward = [math]::Round((@($rows | ForEach-Object { [double]$_.noRewardUpdateGainKm }) | Measure-Object -Sum).Sum, 1)
$causalCases = @($rows | Where-Object { $_.fullBetterThanNoAdaptivePolicy -or $_.fullBetterThanNoMovePriority -or $_.fullBetterThanNoOperatorPolicy -or $_.fullBetterThanNoRewardUpdate }).Count
$adaptivePolicyContributionKm = [math]::Round($totalFull - $totalNoPolicy, 1)
$movePriorityContributionKm = [math]::Round($totalFull - $totalNoMove, 1)
$operatorPolicyContributionKm = [math]::Round($totalFull - $totalNoOperator, 1)
$rewardUpdateContributionKm = [math]::Round($totalFull - $totalNoReward, 1)
$positiveContributionKm = [math]::Round((@(0.0, $adaptivePolicyContributionKm, $movePriorityContributionKm, $operatorPolicyContributionKm, $rewardUpdateContributionKm) | Measure-Object -Maximum).Maximum, 1)

$summary = [pscustomobject]@{
  version = "v0.9.10-A-ml-participation-proof"
  gate = "ml-causal-ablation"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  completed = $rows.Count
  expected = $Datasets.Count
  fullMlGainKm = $totalFull
  heuristicGainKm = $totalHeuristic
  noAdaptivePolicyGainKm = $totalNoPolicy
  noMovePriorityGainKm = $totalNoMove
  noOperatorPolicyGainKm = $totalNoOperator
  noRewardUpdateGainKm = $totalNoReward
  causalContributionKm = $positiveContributionKm
  adaptivePolicyContributionKm = $adaptivePolicyContributionKm
  movePriorityContributionKm = $movePriorityContributionKm
  operatorPolicyContributionKm = $operatorPolicyContributionKm
  rewardUpdateContributionKm = $rewardUpdateContributionKm
  causalContributionCases = $causalCases
  fullBetterThanHeuristicCases = @($rows | Where-Object { $_.fullBetterThanHeuristic }).Count
  fullBetterThanNoAdaptivePolicyCases = @($rows | Where-Object { $_.fullBetterThanNoAdaptivePolicy }).Count
  fullBetterThanNoMovePriorityCases = @($rows | Where-Object { $_.fullBetterThanNoMovePriority }).Count
  fullBetterThanNoOperatorPolicyCases = @($rows | Where-Object { $_.fullBetterThanNoOperatorPolicy }).Count
  fullBetterThanNoRewardUpdateCases = @($rows | Where-Object { $_.fullBetterThanNoRewardUpdate }).Count
  acceptedMutationFromMlTopK = (@($rows | ForEach-Object { [int]$_.acceptedMutationFromMlTopK }) | Measure-Object -Sum).Sum
  rewardUpdates = (@($rows | ForEach-Object { [int]$_.rewardUpdates }) | Measure-Object -Sum).Sum
  pickupDropoffViolations = (@($rows | ForEach-Object { [int]$_.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations = (@($rows | ForEach-Object { [int]$_.capacityViolations }) | Measure-Object -Sum).Sum
  lateRegression = (@($rows | ForEach-Object { [int]$_.lateRegression }) | Measure-Object -Sum).Sum
  coverageRegression = (@($rows | ForEach-Object { [int]$_.coverageRegression }) | Measure-Object -Sum).Sum
  dominanceFailures = @($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict = "POLICY_PARTICIPATION_PROVEN_BUT_CAUSAL_GAIN_NOT_PROVEN"
  overallPass = $false
  rows = $rows
}
$summary.overallPass = $summary.completed -eq $Datasets.Count `
  -and $summary.fullBetterThanHeuristicCases -ge 1 `
  -and $summary.causalContributionCases -ge 1 `
  -and $summary.acceptedMutationFromMlTopK -gt 0 `
  -and $summary.rewardUpdates -gt 0 `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0 `
  -and $summary.dominanceFailures -eq 0
if($summary.overallPass) { $summary.verdict = "ADAPTIVE_POLICY_CAUSAL_CONTRIBUTION_PROVEN" }

$summaryPath = Join-Path $out "ml-causal-ablation-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[ML-CAUSAL-ABLATION] summary=$summaryPath"
if(-not $summary.overallPass) { throw "ML causal ablation gate FAIL verdict=$($summary.verdict)" }
Write-Host "[ML-CAUSAL-ABLATION] PASS"
