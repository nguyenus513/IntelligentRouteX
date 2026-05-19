param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C-greedrl-forecast-fusion-test/greedrl-controller-5case",
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
  Write-Host "[GREEDRL] dataset=$dataset baseline"
  $baseline = Run-Benchmark $dataset "TABULAR_ROUTEFINDER_BASELINE"
  Write-Host "[GREEDRL] dataset=$dataset greedrl"
  $greedrl = Run-Benchmark $dataset "GREEDRL_CONTROLLER_PD_LNS"
  Write-Host "[GREEDRL] dataset=$dataset no-greedrl"
  $noGreedrl = Run-Benchmark $dataset "NO_GREEDRL"
  $pd = Pd $greedrl
  $worker = $pd.mlWorkerProof.workers.greedrl
  $rows += [pscustomobject]@{
    datasetId=$dataset
    baselineGainKm=Gain $baseline
    greedRlGainKm=Gain $greedrl
    noGreedRlGainKm=Gain $noGreedrl
    greedRlBetterThanBaseline=((Gain $greedrl) -gt (Gain $baseline))
    greedRlBetterThanNoGreedRl=((Gain $greedrl) -gt (Gain $noGreedrl))
    greedRlCalled=[bool]$worker.called
    greedRlActionCount=[int]$worker.candidateCount
    greedRlOutputUsed=[bool]$worker.outputUsed
    greedRlAffectedDecisionCount=[int]$worker.affectedDecisionCount
    greedRlAcceptedActionCount=[int]$worker.acceptedCandidateCount
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$greedrl.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}

$summary = [pscustomobject]@{
  version="v0.9.10-C-greedrl-forecast-fusion-test"; gate="greedrl-controller-pd-lns"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  greedRlCalledCases=@($rows | Where-Object greedRlCalled).Count
  greedRlActionCount=(@($rows | ForEach-Object greedRlActionCount) | Measure-Object -Sum).Sum
  greedRlOutputUsedCases=@($rows | Where-Object greedRlOutputUsed).Count
  greedRlAffectedDecisionCount=(@($rows | ForEach-Object greedRlAffectedDecisionCount) | Measure-Object -Sum).Sum
  greedRlAcceptedActionCount=(@($rows | ForEach-Object greedRlAcceptedActionCount) | Measure-Object -Sum).Sum
  greedRlBetterThanBaselineCases=@($rows | Where-Object greedRlBetterThanBaseline).Count
  greedRlBetterThanNoGreedRlCases=@($rows | Where-Object greedRlBetterThanNoGreedRl).Count
  totalBaselineGainKm=[math]::Round((@($rows | ForEach-Object baselineGainKm) | Measure-Object -Sum).Sum, 1)
  totalGreedRlGainKm=[math]::Round((@($rows | ForEach-Object greedRlGainKm) | Measure-Object -Sum).Sum, 1)
  totalNoGreedRlGainKm=[math]::Round((@($rows | ForEach-Object noGreedRlGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  diagnosticPass=$false
  qualityPass=$false
  verdict="GREEDRL_EXPERIMENTAL_CONTROLLER"
  overallPass=$false
  rows=$rows
}
$summary.diagnosticPass = $summary.completed -eq $summary.expected -and $summary.greedRlCalledCases -eq $summary.expected -and $summary.greedRlActionCount -gt 0 -and $summary.greedRlOutputUsedCases -eq $summary.expected -and $summary.greedRlAffectedDecisionCount -gt 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary.qualityPass = $summary.diagnosticPass -and $summary.greedRlBetterThanBaselineCases -ge 1 -and $summary.totalGreedRlGainKm -ge $summary.totalBaselineGainKm
$summary.overallPass = $summary.diagnosticPass
if($summary.qualityPass) { $summary.verdict = "GREEDRL_CONTROLLER_CAUSAL_GAIN_PROVEN" }
elseif($summary.diagnosticPass) { $summary.verdict = "GREEDRL_CONTROLLER_HOT_PATH_PROVEN_NO_AGGREGATE_GAIN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "greedrl-controller-pd-lns-summary.json")
Write-Host "[GREEDRL] summary=$(Join-Path $out 'greedrl-controller-pd-lns-summary.json')"
if(-not $summary.overallPass) { throw "GreedRL controller gate FAIL verdict=$($summary.verdict)" }
Write-Host "[GREEDRL] PASS"
