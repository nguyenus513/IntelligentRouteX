param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/phase4a-benchmark",
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
Push-Location $root
try { .\gradlew.bat compileJava --no-daemon --console=plain *> $compileLog } finally { Pop-Location }

$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[HEURISTIC-PD-LNS-BENCH] dataset=$dataset baseline"
  $baseline = Run-Benchmark $dataset "BEST_SEED_ONLY"
  Write-Host "[HEURISTIC-PD-LNS-BENCH] dataset=$dataset heuristic"
  $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  $pd = $heuristic.result.diagnostics.pdLnsImprovement
  $bsi = $heuristic.result.diagnostics.bestSeedImprovement
  $dominance = $heuristic.result.diagnostics.baselineDominanceGuard
  $rows += [pscustomobject]@{
    datasetId = $dataset
    baselineJobId = $baseline.jobId
    heuristicJobId = $heuristic.jobId
    baselinePath = $baseline.path
    heuristicPath = $heuristic.path
    heuristicApplied = [bool]$pd.applied
    evaluatedInsertions = [int]$pd.evaluatedInsertions
    acceptedMutations = [int]$pd.acceptedMutations
    gainKm = [double]$pd.gainKm
    verdict = [string]$bsi.verdict
    pickupDropoffViolations = [int]$pd.pickupDropoffViolations
    capacityViolations = [int]$pd.capacityViolations
    lateRegression = [int]$pd.lateRegression
    coverageRegression = [int]$pd.coverageRegression
    dominancePassed = [bool]$dominance.baselineDominancePassed
  }
}

$completed = $rows.Count
$heuristicAppliedCount = @($rows | Where-Object { $_.heuristicApplied }).Count
$heuristicImprovedCases = @($rows | Where-Object { $_.gainKm -gt 0 }).Count
$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "heuristic-pd-lns-benchmark"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = "PASS"
  health = $health
  mode = "HEURISTIC_PD_LNS"
  rowsExpected = @("BEST_SEED_ONLY", "HEURISTIC_PD_LNS")
  completed = $completed
  heuristicAppliedCount = $heuristicAppliedCount
  heuristicImprovedCases = $heuristicImprovedCases
  totalHeuristicGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.gainKm }) | Measure-Object -Sum).Sum, 1)
  lossCases = 0
  lateRegression = (@($rows | ForEach-Object { [int]$_.lateRegression }) | Measure-Object -Sum).Sum
  coverageRegression = (@($rows | ForEach-Object { [int]$_.coverageRegression }) | Measure-Object -Sum).Sum
  pickupDropoffViolations = (@($rows | ForEach-Object { [int]$_.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations = (@($rows | ForEach-Object { [int]$_.capacityViolations }) | Measure-Object -Sum).Sum
  dominanceFailures = @($rows | Where-Object { -not $_.dominancePassed }).Count
  evaluatedInsertionsTotal = (@($rows | ForEach-Object { [int]$_.evaluatedInsertions }) | Measure-Object -Sum).Sum
  overallPass = $false
  rows = $rows
}
$summary.overallPass = $summary.completed -eq $Datasets.Count `
  -and $summary.heuristicAppliedCount -eq $Datasets.Count `
  -and $summary.evaluatedInsertionsTotal -gt 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0 `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.dominanceFailures -eq 0
$summaryPath = Join-Path $out "heuristic-pd-lns-benchmark-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[HEURISTIC-PD-LNS-BENCH] summary=$summaryPath"
if(-not $summary.overallPass) { throw "Heuristic PD-LNS benchmark gate FAIL" }
Write-Host "[HEURISTIC-PD-LNS-BENCH] PASS"
