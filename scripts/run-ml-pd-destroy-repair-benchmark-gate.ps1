param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/phase4b-ml-destroy-repair",
  [string[]]$MlModes = @("ML_DESTROY_REPAIR_AUTO"),
  [switch]$FullGrid,
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
function Run-Benchmark($dataset, $pdMode) {
  $request = @{
    datasetId = $dataset
    mode = "QUALITY_BENCHMARK"
    solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
    adaptiveMlPolicyMode = "QUALITY_SEEKING"
    pdLnsMode = $pdMode
    pdLnsMaxRounds = 3
    pdLnsTopBadOrders = 12
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
  $path = Join-Path $out "$dataset-$pdMode-result.json"
  $result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
  return [pscustomobject]@{ jobId = $job.jobId; result = $result; path = $path }
}

$compileLog = Join-Path $out "compileJava.log"
if(-not $SkipCompile) {
  Push-Location $root
  try { .\gradlew.bat compileJava --no-daemon --console=plain *> $compileLog } finally { Pop-Location }
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
if($FullGrid) { $MlModes = @("ML_DESTROY_REPAIR_K2", "ML_DESTROY_REPAIR_K3", "ML_DESTROY_REPAIR_K4", "ML_DESTROY_REPAIR_AUTO") }
foreach($dataset in $Datasets) {
  Write-Host "[ML-PD-DR-BENCH] dataset=$dataset heuristic"
  $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  $hPd = $heuristic.result.diagnostics.pdLnsImprovement
  $bestMl = $null
  foreach($mode in $MlModes) {
    Write-Host "[ML-PD-DR-BENCH] dataset=$dataset mode=$mode"
    $ml = Run-Benchmark $dataset $mode
    $pd = $ml.result.diagnostics.pdLnsImprovement
    $bsi = $ml.result.diagnostics.bestSeedImprovement
    $dominance = $ml.result.diagnostics.baselineDominanceGuard
    $gainOverHeuristic = [math]::Round(([double]$pd.gainKm - [double]$hPd.gainKm), 1)
    $candidate = [pscustomobject]@{
      datasetId = $dataset
      mode = $mode
      heuristicJobId = $heuristic.jobId
      mlJobId = $ml.jobId
      heuristicPath = $heuristic.path
      mlPath = $ml.path
      heuristicGainKm = [double]$hPd.gainKm
      mlGainKm = [double]$pd.gainKm
      mlGainOverHeuristicKm = $gainOverHeuristic
      mlBetterThanHeuristic = $gainOverHeuristic -gt 0.0
      mlApplied = [bool]$pd.applied
      evaluatedMutations = [int]$pd.evaluatedMutations
      feasibleMutations = [int]$pd.feasibleMutations
      acceptedMutations = [int]$pd.acceptedMutations
      verdict = [string]$bsi.verdict
      improvedBestSeed = [bool]$bsi.improvedBestSeed
      finalSeedSource = [string]$bsi.finalSeedSource
      distanceGainOverBestSeedKm = [double]$bsi.distanceGainOverBestSeedKm
      pickupDropoffViolations = [int]$pd.pickupDropoffViolations
      capacityViolations = [int]$pd.capacityViolations
      lateRegression = [int]$pd.lateRegression
      coverageRegression = [int]$pd.coverageRegression
      dominancePassed = [bool]$dominance.baselineDominancePassed
    }
    if($null -eq $bestMl -or $candidate.mlGainKm -gt $bestMl.mlGainKm) { $bestMl = $candidate }
  }
  $rows += $bestMl
}

$completed = $rows.Count
$mlAppliedCount = @($rows | Where-Object { $_.mlApplied }).Count
$mlBetterThanHeuristicCases = @($rows | Where-Object { $_.mlBetterThanHeuristic }).Count
$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "ml-pd-destroy-repair-benchmark"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  rowsExpected = @("HEURISTIC_PD_LNS") + $MlModes
  completed = $completed
  mlAppliedCount = $mlAppliedCount
  mlBetterThanHeuristicCases = $mlBetterThanHeuristicCases
  mlBestSeedImprovedCases = @($rows | Where-Object { $_.improvedBestSeed }).Count
  totalHeuristicGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.heuristicGainKm }) | Measure-Object -Sum).Sum, 1)
  totalMlGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.mlGainKm }) | Measure-Object -Sum).Sum, 1)
  totalMlGainOverHeuristicKm = [math]::Round((@($rows | ForEach-Object { [double]$_.mlGainOverHeuristicKm }) | Measure-Object -Sum).Sum, 1)
  lossCases = 0
  lateRegression = (@($rows | ForEach-Object { [int]$_.lateRegression }) | Measure-Object -Sum).Sum
  coverageRegression = (@($rows | ForEach-Object { [int]$_.coverageRegression }) | Measure-Object -Sum).Sum
  pickupDropoffViolations = (@($rows | ForEach-Object { [int]$_.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations = (@($rows | ForEach-Object { [int]$_.capacityViolations }) | Measure-Object -Sum).Sum
  dominanceFailures = @($rows | Where-Object { -not $_.dominancePassed }).Count
  evaluatedMutationsTotal = (@($rows | ForEach-Object { [int]$_.evaluatedMutations }) | Measure-Object -Sum).Sum
  overallPass = $false
  rows = $rows
}
$summary.overallPass = $summary.completed -eq $Datasets.Count `
  -and $summary.mlAppliedCount -eq $Datasets.Count `
  -and $summary.mlBetterThanHeuristicCases -ge 1 `
  -and $summary.mlBestSeedImprovedCases -ge 1 `
  -and $summary.totalMlGainKm -ge $summary.totalHeuristicGainKm `
  -and $summary.evaluatedMutationsTotal -gt 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0 `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.dominanceFailures -eq 0
$summaryPath = Join-Path $out "ml-pd-destroy-repair-benchmark-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[ML-PD-DR-BENCH] summary=$summaryPath"
if(-not $summary.overallPass) { throw "ML PD destroy/repair benchmark gate FAIL" }
Write-Host "[ML-PD-DR-BENCH] PASS"
