param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/routefinder-provider-5case",
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

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[ROUTEFINDER-PROVIDER] dataset=$dataset policy"; $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  Write-Host "[ROUTEFINDER-PROVIDER] dataset=$dataset tabular"; $tabular = Run-Benchmark $dataset "TABULAR_WEIGHT_075"
  Write-Host "[ROUTEFINDER-PROVIDER] dataset=$dataset routefinder"; $routefinder = Run-Benchmark $dataset "ROUTEFINDER_ASSISTED_PD_LNS"
  Write-Host "[ROUTEFINDER-PROVIDER] dataset=$dataset tabular-routefinder"; $hybrid = Run-Benchmark $dataset "TABULAR_ROUTEFINDER_PD_LNS"
  $pd = Pd $routefinder; $worker = $pd.mlWorkerProof.workers.routefinder
  $hpd = Pd $hybrid; $hworker = $hpd.mlWorkerProof.workers.routefinder
  $bestRoutefinderGain = [math]::Max((Gain $routefinder), (Gain $hybrid))
  $baselineGain = [math]::Max((Gain $policy), (Gain $tabular))
  $rows += [pscustomobject]@{
    datasetId=$dataset
    policyOnlyGainKm=Gain $policy
    tabularGainKm=Gain $tabular
    routefinderGainKm=Gain $routefinder
    tabularRoutefinderGainKm=Gain $hybrid
    bestRoutefinderGainKm=$bestRoutefinderGain
    bestBaselineGainKm=$baselineGain
    routefinderBetterThanPolicyOrTabular=$bestRoutefinderGain -gt $baselineGain
    routefinderCalled=[bool]$worker.called -or [bool]$hworker.called
    routefinderInferenceCount=[int]$worker.inferenceCount + [int]$hworker.inferenceCount
    routefinderCandidateCount=[int]$worker.candidateCount + [int]$hworker.candidateCount
    routefinderOutputUsed=[bool]$worker.outputUsed -or [bool]$hworker.outputUsed
    routefinderAffectedDecisionCount=[int]$worker.affectedDecisionCount + [int]$hworker.affectedDecisionCount
    routefinderAcceptedCandidateCount=[int]$worker.acceptedCandidateCount + [int]$hworker.acceptedCandidateCount
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations + [int]$hpd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations + [int]$hpd.capacityViolations
    lateRegression=[int]$pd.lateRegression + [int]$hpd.lateRegression
    coverageRegression=[int]$pd.coverageRegression + [int]$hpd.coverageRegression
    dominancePassed=([bool]$routefinder.result.diagnostics.baselineDominanceGuard.baselineDominancePassed -and [bool]$hybrid.result.diagnostics.baselineDominanceGuard.baselineDominancePassed)
  }
}
$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="routefinder-candidate-provider"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  routefinderCalledCases=@($rows | Where-Object routefinderCalled).Count
  routefinderInferenceCount=(@($rows | ForEach-Object routefinderInferenceCount) | Measure-Object -Sum).Sum
  routefinderCandidateCount=(@($rows | ForEach-Object routefinderCandidateCount) | Measure-Object -Sum).Sum
  routefinderOutputUsedCases=@($rows | Where-Object routefinderOutputUsed).Count
  routefinderAffectedDecisionCount=(@($rows | ForEach-Object routefinderAffectedDecisionCount) | Measure-Object -Sum).Sum
  routefinderAcceptedCandidateCount=(@($rows | ForEach-Object routefinderAcceptedCandidateCount) | Measure-Object -Sum).Sum
  routefinderBetterThanPolicyOrTabularCases=@($rows | Where-Object routefinderBetterThanPolicyOrTabular).Count
  totalBaselineGainKm=[math]::Round((@($rows | ForEach-Object bestBaselineGainKm) | Measure-Object -Sum).Sum, 1)
  totalRoutefinderGainKm=[math]::Round((@($rows | ForEach-Object bestRoutefinderGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="ROUTEFINDER_PROVIDER_NO_CAUSAL_GAIN"
  overallPass=$false
  rows=$rows
}
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.routefinderCalledCases -ge 1 -and $summary.routefinderCandidateCount -gt 0 -and $summary.routefinderOutputUsedCases -ge 1 -and $summary.routefinderAcceptedCandidateCount -ge 1 -and $summary.routefinderBetterThanPolicyOrTabularCases -ge 1 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
if($summary.overallPass) { $summary.verdict = "ROUTEFINDER_PROVIDER_CAUSAL_GAIN_PROVEN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "routefinder-candidate-provider-summary.json")
Write-Host "[ROUTEFINDER-PROVIDER] summary=$(Join-Path $out 'routefinder-candidate-provider-summary.json')"
if(-not $summary.overallPass) { throw "RouteFinder provider gate FAIL verdict=$($summary.verdict)" }
Write-Host "[ROUTEFINDER-PROVIDER] PASS"
