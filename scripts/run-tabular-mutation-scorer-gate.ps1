param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/tabular-scorer-5case",
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
  Write-Host "[TABULAR-SCORER] dataset=$dataset policy"; $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  Write-Host "[TABULAR-SCORER] dataset=$dataset tabular"; $tabular = Run-Benchmark $dataset "TABULAR_SCORED_PD_LNS"
  Write-Host "[TABULAR-SCORER] dataset=$dataset no-tabular"; $noTabular = Run-Benchmark $dataset "NO_TABULAR_PD_LNS"
  $pd = Pd $tabular; $worker = $pd.mlWorkerProof.workers.tabular
  $rows += [pscustomobject]@{
    datasetId=$dataset
    policyOnlyGainKm=Gain $policy
    tabularGainKm=Gain $tabular
    noTabularGainKm=Gain $noTabular
    tabularBetterThanPolicyOnly=((Gain $tabular) -gt (Gain $policy))
    tabularBetterThanNoTabular=((Gain $tabular) -gt (Gain $noTabular))
    tabularCalled=[bool]$worker.called
    tabularInferenceCount=[int]$worker.inferenceCount
    tabularCandidateCount=[int]$worker.candidateCount
    tabularOutputUsed=[bool]$worker.outputUsed
    tabularAffectedDecisionCount=[int]$worker.affectedDecisionCount
    tabularAcceptedCandidateCount=[int]$worker.acceptedCandidateCount
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$tabular.result.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}
$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="tabular-mutation-scorer"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  tabularCalledCases=@($rows | Where-Object tabularCalled).Count
  tabularInferenceCount=(@($rows | ForEach-Object tabularInferenceCount) | Measure-Object -Sum).Sum
  tabularCandidateCount=(@($rows | ForEach-Object tabularCandidateCount) | Measure-Object -Sum).Sum
  tabularOutputUsedCases=@($rows | Where-Object tabularOutputUsed).Count
  tabularAffectedDecisionCount=(@($rows | ForEach-Object tabularAffectedDecisionCount) | Measure-Object -Sum).Sum
  tabularAcceptedCandidateCount=(@($rows | ForEach-Object tabularAcceptedCandidateCount) | Measure-Object -Sum).Sum
  tabularBetterThanPolicyOnlyCases=@($rows | Where-Object tabularBetterThanPolicyOnly).Count
  tabularBetterThanNoTabularCases=@($rows | Where-Object tabularBetterThanNoTabular).Count
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  diagnosticPass=$false
  contributionPass=$false
  verdict="TABULAR_MUTATION_SCORER_NO_GAIN"
  overallPass=$false; rows=$rows
}
$summary.diagnosticPass = $summary.completed -eq $summary.expected -and $summary.tabularCalledCases -eq $summary.expected -and $summary.tabularInferenceCount -gt 0 -and $summary.tabularOutputUsedCases -ge 1 -and $summary.tabularAffectedDecisionCount -gt 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary.contributionPass = $summary.diagnosticPass -and $summary.tabularBetterThanPolicyOnlyCases -ge 1
$summary.overallPass = $summary.diagnosticPass
if($summary.contributionPass) { $summary.verdict = "TABULAR_MUTATION_SCORER_CONTRIBUTION_PROVEN" }
elseif($summary.diagnosticPass) { $summary.verdict = "TABULAR_MUTATION_SCORER_HOT_PATH_PROVEN_NO_QUALITY_GAIN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "tabular-mutation-scorer-summary.json")
Write-Host "[TABULAR-SCORER] summary=$(Join-Path $out 'tabular-mutation-scorer-summary.json')"
if(-not $summary.overallPass) { throw "Tabular mutation scorer gate FAIL verdict=$($summary.verdict)" }
Write-Host "[TABULAR-SCORER] PASS"
