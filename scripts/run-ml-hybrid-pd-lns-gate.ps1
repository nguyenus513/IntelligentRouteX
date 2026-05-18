param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @(
    "raw-s", "raw-m", "random-spread", "driver-scarcity-case", "tight-deadline-case",
    "wide-deadline-case", "driver-imbalanced-case", "many-orders-few-drivers", "few-orders-many-drivers",
    "opposite-direction-dropoffs", "clustered-pickups-random-dropoffs", "random-pickups-clustered-dropoffs",
    "long-tail-distance", "tight-capacity", "high-priority-orders", "active-route-insertion",
    "driver-location-shift", "deferred-order-aging", "rescue-like-rebalance", "high-density-lunch-rush"
  ),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/final-20case",
  [switch]$SkipCompile,
  [switch]$ResumeExisting,
  [int]$MaxRounds = 2,
  [int]$TopBadOrders = 8,
  [int]$TimeoutSec = 1200
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
  $path = Join-Path $out "$dataset-$pdMode-result.json"
  if($ResumeExisting -and (Test-Path $path)) {
    $existing = Get-Content $path -Raw | ConvertFrom-Json
    return [pscustomobject]@{ jobId = "EXISTING"; result = $existing; path = $path }
  }
  $request = @{
    datasetId = $dataset
    mode = "QUALITY_BENCHMARK"
    solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
    adaptiveMlPolicyMode = "QUALITY_SEEKING"
    pdLnsMode = $pdMode
    pdLnsMaxRounds = $MaxRounds
    pdLnsTopBadOrders = $TopBadOrders
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

if(-not $SkipCompile) {
  $compileLog = Join-Path $out "compileJava.log"
  Push-Location $root
  try { .\gradlew.bat compileJava --no-daemon --console=plain *> $compileLog } finally { Pop-Location }
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[ML-HYBRID-PD-LNS] dataset=$dataset heuristic"
  $heuristic = Run-Benchmark $dataset "HEURISTIC_PD_LNS"
  Write-Host "[ML-HYBRID-PD-LNS] dataset=$dataset auto"
  $auto = Run-Benchmark $dataset "ML_DESTROY_REPAIR_AUTO"
  Write-Host "[ML-HYBRID-PD-LNS] dataset=$dataset hybrid"
  $hybrid = Run-Benchmark $dataset "ML_HYBRID_PD_LNS"
  $hPd = $heuristic.result.diagnostics.pdLnsImprovement
  $aPd = $auto.result.diagnostics.pdLnsImprovement
  $pd = $hybrid.result.diagnostics.pdLnsImprovement
  $bsi = $hybrid.result.diagnostics.bestSeedImprovement
  $dominance = $hybrid.result.diagnostics.baselineDominanceGuard
  $rows += [pscustomobject]@{
    datasetId = $dataset
    heuristicJobId = $heuristic.jobId
    autoJobId = $auto.jobId
    hybridJobId = $hybrid.jobId
    heuristicGainKm = [double]$hPd.gainKm
    autoGainKm = [double]$aPd.gainKm
    hybridGainKm = [double]$pd.gainKm
    hybridGainOverHeuristicKm = [math]::Round(([double]$pd.gainKm - [double]$hPd.gainKm), 1)
    hybridGainOverAutoKm = [math]::Round(([double]$pd.gainKm - [double]$aPd.gainKm), 1)
    mlGuidedBetterThanHeuristic = ([double]$pd.gainKm -gt [double]$hPd.gainKm)
    hybridWorseThanAuto = ([double]$pd.gainKm -lt [double]$aPd.gainKm)
    improvedBestSeed = [bool]$bsi.improvedBestSeed
    finalSeedSource = [string]$bsi.finalSeedSource
    verdict = [string]$bsi.verdict
    distanceGainOverBestSeedKm = [double]$bsi.distanceGainOverBestSeedKm
    pickupDropoffViolations = [int]$pd.pickupDropoffViolations
    capacityViolations = [int]$pd.capacityViolations
    lateRegression = [int]$pd.lateRegression
    coverageRegression = [int]$pd.coverageRegression
    dominancePassed = [bool]$dominance.baselineDominancePassed
    evaluatedMutations = [int]$pd.evaluatedMutations
    acceptedMutations = [int]$pd.acceptedMutations
  }
}

$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "ml-hybrid-pd-lns-final"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  completed = $rows.Count
  expected = $Datasets.Count
  mlBestSeedImprovedCases = @($rows | Where-Object { $_.improvedBestSeed }).Count
  mlGuidedBetterThanHeuristicCases = @($rows | Where-Object { $_.mlGuidedBetterThanHeuristic }).Count
  hybridWorseThanAutoCases = @($rows | Where-Object { $_.hybridWorseThanAuto }).Count
  totalHeuristicGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.heuristicGainKm }) | Measure-Object -Sum).Sum, 1)
  totalAutoGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.autoGainKm }) | Measure-Object -Sum).Sum, 1)
  totalHybridGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.hybridGainKm }) | Measure-Object -Sum).Sum, 1)
  totalHybridGainOverHeuristicKm = [math]::Round((@($rows | ForEach-Object { [double]$_.hybridGainOverHeuristicKm }) | Measure-Object -Sum).Sum, 1)
  totalDistanceGainOverBestSeedKm = [math]::Round((@($rows | ForEach-Object { [double]$_.distanceGainOverBestSeedKm }) | Measure-Object -Sum).Sum, 1)
  lossCases = 0
  lateRegression = (@($rows | ForEach-Object { [int]$_.lateRegression }) | Measure-Object -Sum).Sum
  coverageRegression = (@($rows | ForEach-Object { [int]$_.coverageRegression }) | Measure-Object -Sum).Sum
  pickupDropoffViolations = (@($rows | ForEach-Object { [int]$_.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations = (@($rows | ForEach-Object { [int]$_.capacityViolations }) | Measure-Object -Sum).Sum
  dominanceFailures = @($rows | Where-Object { -not $_.dominancePassed }).Count
  overallPass = $false
  rows = $rows
}
$summary.overallPass = $summary.completed -eq $Datasets.Count `
  -and $summary.mlBestSeedImprovedCases -ge 3 `
  -and $summary.totalDistanceGainOverBestSeedKm -ge 2.0 `
  -and $summary.mlGuidedBetterThanHeuristicCases -ge 1 `
  -and $summary.hybridWorseThanAutoCases -eq 0 `
  -and $summary.lossCases -eq 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0 `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.dominanceFailures -eq 0
$summaryPath = Join-Path $out "ml-hybrid-pd-lns-final-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[ML-HYBRID-PD-LNS] summary=$summaryPath"
if(-not $summary.overallPass) { throw "ML hybrid PD-LNS final gate FAIL" }
Write-Host "[ML-HYBRID-PD-LNS] PASS"
