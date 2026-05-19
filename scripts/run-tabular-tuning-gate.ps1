param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/tabular-tuning-5case",
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
$modes = @("TABULAR_WEIGHT_025", "TABULAR_WEIGHT_050", "TABULAR_WEIGHT_075", "TABULAR_ONLY_SCORER")
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[TABULAR-TUNING] dataset=$dataset policy"; $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  foreach($mode in $modes) {
    Write-Host "[TABULAR-TUNING] dataset=$dataset mode=$mode"
    $run = Run-Benchmark $dataset $mode
    $pd = Pd $run; $worker = $pd.mlWorkerProof.workers.tabular
    $rows += [pscustomobject]@{
      datasetId=$dataset
      mode=$mode
      policyOnlyGainKm=Gain $policy
      tabularGainKm=Gain $run
      gainOverPolicyKm=[math]::Round((Gain $run) - (Gain $policy), 1)
      tabularBetterThanPolicyOnly=((Gain $run) -gt (Gain $policy))
      tabularCalled=[bool]$worker.called
      tabularInferenceCount=[int]$worker.inferenceCount
      tabularOutputUsed=[bool]$worker.outputUsed
      tabularAffectedDecisionCount=[int]$worker.affectedDecisionCount
      tabularAcceptedCandidateCount=[int]$worker.acceptedCandidateCount
      pickupDropoffViolations=[int]$pd.pickupDropoffViolations
      capacityViolations=[int]$pd.capacityViolations
      lateRegression=[int]$pd.lateRegression
      coverageRegression=[int]$pd.coverageRegression
      dominancePassed=[bool]$run.result.diagnostics.baselineDominanceGuard.baselineDominancePassed
    }
  }
}
$bestRows = $rows | Group-Object datasetId | ForEach-Object { $_.Group | Sort-Object tabularGainKm -Descending | Select-Object -First 1 }
$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="tabular-tuning"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completedDatasets=$Datasets.Count
  completedRows=$rows.Count
  expectedRows=$Datasets.Count * $modes.Count
  tabularCalledRows=@($rows | Where-Object tabularCalled).Count
  tabularInferenceCount=(@($rows | ForEach-Object tabularInferenceCount) | Measure-Object -Sum).Sum
  tabularOutputUsedRows=@($rows | Where-Object tabularOutputUsed).Count
  tabularAffectedDecisionCount=(@($rows | ForEach-Object tabularAffectedDecisionCount) | Measure-Object -Sum).Sum
  tabularAcceptedCandidateCount=(@($rows | ForEach-Object tabularAcceptedCandidateCount) | Measure-Object -Sum).Sum
  tabularBetterThanPolicyOnlyCases=@($bestRows | Where-Object tabularBetterThanPolicyOnly).Count
  bestTotalPolicyGainKm=[math]::Round((@($bestRows | ForEach-Object policyOnlyGainKm) | Measure-Object -Sum).Sum, 1)
  bestTotalTabularGainKm=[math]::Round((@($bestRows | ForEach-Object tabularGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="TABULAR_TUNING_NO_CAUSAL_GAIN"
  overallPass=$false
  bestRows=$bestRows
  rows=$rows
}
$summary.overallPass = $summary.completedRows -eq $summary.expectedRows -and $summary.tabularCalledRows -eq $summary.expectedRows -and $summary.tabularInferenceCount -gt 0 -and $summary.tabularOutputUsedRows -eq $summary.expectedRows -and $summary.tabularAffectedDecisionCount -gt 0 -and $summary.tabularBetterThanPolicyOnlyCases -ge 1 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
if($summary.overallPass) { $summary.verdict = "TABULAR_TUNING_CAUSAL_GAIN_PROVEN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "tabular-tuning-summary.json")
Write-Host "[TABULAR-TUNING] summary=$(Join-Path $out 'tabular-tuning-summary.json')"
if(-not $summary.overallPass) { throw "Tabular tuning gate FAIL verdict=$($summary.verdict)" }
Write-Host "[TABULAR-TUNING] PASS"
