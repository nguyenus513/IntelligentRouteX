param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C-tri-model-fusion/ablation-5case",
  [string]$FusionDir = "artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case",
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
  if(Test-Path $path) { return Get-Content $path -Raw | ConvertFrom-Json }
  $source = Join-Path $root (Join-Path $FusionDir "$dataset-$pdMode-result.json")
  if(Test-Path $source) {
    Copy-Item $source $path -Force
    return Get-Content $path -Raw | ConvertFrom-Json
  }
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
function Gain($result) { [double]$result.diagnostics.pdLnsImprovement.gainKm }
function Pd($result) { $result.diagnostics.pdLnsImprovement }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[TRI-ABLATION] dataset=$dataset"
  $fusion = Run-Benchmark $dataset "TRI_MODEL_FUSION_PD_LNS"
  $noTabular = Run-Benchmark $dataset "TRI_MODEL_FUSION_NO_TABULAR"
  $noRoutefinder = Run-Benchmark $dataset "TRI_MODEL_FUSION_NO_ROUTEFINDER"
  $noGreedrl = Run-Benchmark $dataset "TRI_MODEL_FUSION_NO_GREEDRL"
  $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  $pd = Pd $fusion
  $workers = $pd.mlWorkerProof.workers
  $rows += [pscustomobject]@{
    datasetId=$dataset
    fusionGainKm=Gain $fusion
    noTabularGainKm=Gain $noTabular
    noRoutefinderGainKm=Gain $noRoutefinder
    noGreedRlGainKm=Gain $noGreedrl
    policyOnlyGainKm=Gain $policy
    heuristicGainKm=Gain $heuristic
    tabularAblationLoss=((Gain $fusion) -gt (Gain $noTabular))
    routefinderAblationLoss=((Gain $fusion) -gt (Gain $noRoutefinder))
    greedRlAblationLoss=((Gain $fusion) -gt (Gain $noGreedrl))
    noGreedRlBetterThanFusion=((Gain $noGreedrl) -gt (Gain $fusion))
    forecastCalled=[bool]$workers.forecast.called
    tabularCalled=[bool]$workers.tabular.called
    routefinderCalled=[bool]$workers.routefinder.called
    greedRlCalled=[bool]$workers.greedrl.called
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$fusion.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}

$workerContributionCount = 0
if(@($rows | Where-Object tabularAblationLoss).Count -gt 0) { $workerContributionCount++ }
if(@($rows | Where-Object routefinderAblationLoss).Count -gt 0) { $workerContributionCount++ }
if(@($rows | Where-Object greedRlAblationLoss).Count -gt 0) { $workerContributionCount++ }

$summary = [pscustomobject]@{
  version="v0.9.10-C-tri-model-fusion"; gate="tri-model-causal-ablation"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  atLeastOneModelAblationLoss=@($rows | Where-Object { $_.tabularAblationLoss -or $_.routefinderAblationLoss -or $_.greedRlAblationLoss }).Count -ge 1
  modelWorkersWithContribution=$workerContributionCount
  atLeastTwoModelWorkersHaveContribution=$false
  tabularAblationLossCases=@($rows | Where-Object tabularAblationLoss).Count
  routefinderAblationLossCases=@($rows | Where-Object routefinderAblationLoss).Count
  greedRlAblationLossCases=@($rows | Where-Object greedRlAblationLoss).Count
  noGreedRlBetterThanFusionCases=@($rows | Where-Object noGreedRlBetterThanFusion).Count
  forecastCalledCases=@($rows | Where-Object forecastCalled).Count
  totalFusionGainKm=[math]::Round((@($rows | ForEach-Object fusionGainKm) | Measure-Object -Sum).Sum, 1)
  totalNoTabularGainKm=[math]::Round((@($rows | ForEach-Object noTabularGainKm) | Measure-Object -Sum).Sum, 1)
  totalNoRoutefinderGainKm=[math]::Round((@($rows | ForEach-Object noRoutefinderGainKm) | Measure-Object -Sum).Sum, 1)
  totalNoGreedRlGainKm=[math]::Round((@($rows | ForEach-Object noGreedRlGainKm) | Measure-Object -Sum).Sum, 1)
  totalPolicyOnlyGainKm=[math]::Round((@($rows | ForEach-Object policyOnlyGainKm) | Measure-Object -Sum).Sum, 1)
  totalHeuristicGainKm=[math]::Round((@($rows | ForEach-Object heuristicGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="TRI_MODEL_ABLATION_NOT_PROVEN"
  overallPass=$false
  rows=$rows
}
$summary.atLeastTwoModelWorkersHaveContribution = $summary.modelWorkersWithContribution -ge 2
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.atLeastOneModelAblationLoss -and $summary.forecastCalledCases -eq 0 -and $summary.noGreedRlBetterThanFusionCases -eq 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
if($summary.overallPass -and $summary.atLeastTwoModelWorkersHaveContribution) { $summary.verdict = "TRI_MODEL_CAUSAL_ABLATION_PROVEN" }
elseif($summary.overallPass) { $summary.verdict = "TRI_MODEL_CAUSAL_ABLATION_PARTIAL" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "tri-model-causal-ablation-summary.json")
Write-Host "[TRI-ABLATION] summary=$(Join-Path $out 'tri-model-causal-ablation-summary.json')"
if(-not $summary.overallPass) { throw "Tri-model causal ablation gate FAIL verdict=$($summary.verdict)" }
Write-Host "[TRI-ABLATION] PASS"
