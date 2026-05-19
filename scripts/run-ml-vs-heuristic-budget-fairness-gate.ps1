param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [int[]]$BudgetsMs = @(500, 1000, 3000),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-B-ml-core-proof/budget-fairness-5case",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) { Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec $timeout }
function Run-Benchmark([string]$dataset, [string]$pdMode, [int]$budgetMs) {
  $path = Join-Path $out "$dataset-$pdMode-${budgetMs}ms-result.json"
  if(Test-Path $path) {
    return Get-Content $path -Raw | ConvertFrom-Json
  }
  $request = @{ datasetId=$dataset; mode="QUALITY_BENCHMARK"; solvers=@("OR-Tools","PyVRP","VROOM","IntelligentRouteX"); adaptiveMlPolicyMode="QUALITY_SEEKING"; pdLnsMode=$pdMode; pdLnsMaxRounds=2; pdLnsTopBadOrders=8; pdLnsBudgetMs=$budgetMs }
  $started = Get-Date
  $job = Post-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs" $request $TimeoutSec
  $result = $null; $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while((Get-Date) -lt $deadline) {
    try { $result = Get-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" 120; if($result.status -eq "COMPLETED" -or $result.runStatus -eq "COMPLETED" -or $result.status -eq "FAILED" -or $result.runStatus -eq "FAILED") { break } } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2
  }
  $elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
  if($null -eq $result) { throw "timeout dataset=$dataset mode=$pdMode budgetMs=$budgetMs job=$($job.jobId)" }
  $envelope = [pscustomobject]@{ budgetMs=$budgetMs; pdLnsMode=$pdMode; elapsedMs=$elapsedMs; jobId=$job.jobId; result=$result }
  $envelope | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
  return $envelope
}
function Pd($run) { $run.result.diagnostics.pdLnsImprovement }
function Gain($run) { [double](Pd $run).gainKm }
function Mutations($run) { [int](Pd $run).evaluatedMutations }
function Accepted($run) { [int](Pd $run).acceptedMutations }
function GainPerSecond($run) { if($run.elapsedMs -le 0) { return 0.0 }; [math]::Round((Gain $run) / ($run.elapsedMs / 1000.0), 3) }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = Get-Json "$BaseUrl/api/v1/health" 30
$mlModes = @("TABULAR_WEIGHT_075", "ROUTEFINDER_ASSISTED_PD_LNS", "TABULAR_ROUTEFINDER_PD_LNS")
$rows = @()
foreach($dataset in $Datasets) {
  foreach($budget in $BudgetsMs) {
    Write-Host "[BUDGET-FAIRNESS] dataset=$dataset budget=${budget} heuristic"
    $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS" $budget
    $mlRuns = @()
    foreach($mode in $mlModes) {
      Write-Host "[BUDGET-FAIRNESS] dataset=$dataset budget=${budget} ml=$mode"
      $mlRuns += Run-Benchmark $dataset $mode $budget
    }
    $mlBest = $mlRuns | Sort-Object { Gain $_ } -Descending | Select-Object -First 1
    $pd = Pd $mlBest
    $heuristicRate = if((Mutations $heuristic) -le 0) { 0.0 } else { [math]::Round((Accepted $heuristic) / [double](Mutations $heuristic), 4) }
    $mlRate = if((Mutations $mlBest) -le 0) { 0.0 } else { [math]::Round((Accepted $mlBest) / [double](Mutations $mlBest), 4) }
    $rows += [pscustomobject]@{
      datasetId=$dataset
      budgetMs=$budget
      heuristicMode="HEURISTIC_PD_LNS"
      mlMode=$mlBest.pdLnsMode
      heuristicGainKm=Gain $heuristic
      mlGainKm=Gain $mlBest
      heuristicRuntimeMs=$heuristic.elapsedMs
      mlRuntimeMs=$mlBest.elapsedMs
      heuristicEvaluatedMutations=Mutations $heuristic
      mlEvaluatedMutations=Mutations $mlBest
      heuristicAcceptedMutationRate=$heuristicRate
      mlAcceptedMutationRate=$mlRate
      heuristicGainPerSecond=GainPerSecond $heuristic
      mlGainPerSecond=GainPerSecond $mlBest
      mlBetterSameBudget=((Gain $mlBest) -gt (Gain $heuristic))
      mlGainPerSecondBetter=((GainPerSecond $mlBest) -gt (GainPerSecond $heuristic))
      pickupDropoffViolations=[int]$pd.pickupDropoffViolations
      capacityViolations=[int]$pd.capacityViolations
      lateRegression=[int]$pd.lateRegression
      coverageRegression=[int]$pd.coverageRegression
      dominancePassed=[bool]$mlBest.result.diagnostics.baselineDominanceGuard.baselineDominancePassed
    }
  }
}

$perDataset = $rows | Group-Object datasetId | ForEach-Object {
  $group = $_.Group
  [pscustomobject]@{
    datasetId=$_.Name
    mlBetterSameBudgetAny=@($group | Where-Object mlBetterSameBudget).Count -gt 0
    mlGainPerSecondBetterAny=@($group | Where-Object mlGainPerSecondBetter).Count -gt 0
    bestMlGainKm=(@($group | ForEach-Object mlGainKm) | Measure-Object -Maximum).Maximum
    bestHeuristicGainKm=(@($group | ForEach-Object heuristicGainKm) | Measure-Object -Maximum).Maximum
  }
}

$summary = [pscustomobject]@{
  version="v0.9.10-B-ml-core-proof"; gate="ml-vs-heuristic-budget-fairness"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$perDataset.Count; expected=$Datasets.Count
  completedRows=$rows.Count; expectedRows=$Datasets.Count * $BudgetsMs.Count
  mlBetterSameBudgetCases=@($perDataset | Where-Object mlBetterSameBudgetAny).Count
  mlGainPerSecondBetterCases=@($perDataset | Where-Object mlGainPerSecondBetterAny).Count
  mlBetterSameBudgetRows=@($rows | Where-Object mlBetterSameBudget).Count
  mlGainPerSecondBetterRows=@($rows | Where-Object mlGainPerSecondBetter).Count
  totalBestMlGainKm=[math]::Round((@($perDataset | ForEach-Object bestMlGainKm) | Measure-Object -Sum).Sum, 1)
  totalBestHeuristicGainKm=[math]::Round((@($perDataset | ForEach-Object bestHeuristicGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="ML_BUDGET_FAIRNESS_NOT_PROVEN"
  overallPass=$false
  perDataset=$perDataset
  rows=$rows
}
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.mlBetterSameBudgetCases -ge 1 -and $summary.mlGainPerSecondBetterCases -ge 2 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
if($summary.overallPass) { $summary.verdict = "ML_BUDGET_FAIRNESS_PROVEN_SELECTED_CASES" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "ml-vs-heuristic-budget-fairness-summary.json")
Write-Host "[BUDGET-FAIRNESS] summary=$(Join-Path $out 'ml-vs-heuristic-budget-fairness-summary.json')"
if(-not $summary.overallPass) { throw "ML budget fairness gate FAIL verdict=$($summary.verdict)" }
Write-Host "[BUDGET-FAIRNESS] PASS"
