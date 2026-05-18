param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-guided-pd-lns/phase5-cross-swapstar",
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
  $path = Join-Path $out "$dataset-$pdMode-result.json"
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
  Write-Host "[PD-CROSS-SWAPSTAR] dataset=$dataset auto"
  $auto = Run-Benchmark $dataset "ML_DESTROY_REPAIR_AUTO"
  Write-Host "[PD-CROSS-SWAPSTAR] dataset=$dataset hybrid"
  $hybrid = Run-Benchmark $dataset "ML_HYBRID_PD_LNS"
  $autoPd = $auto.result.diagnostics.pdLnsImprovement
  $pd = $hybrid.result.diagnostics.pdLnsImprovement
  $bsi = $hybrid.result.diagnostics.bestSeedImprovement
  $dominance = $hybrid.result.diagnostics.baselineDominanceGuard
  $rows += [pscustomobject]@{
    datasetId = $dataset
    autoJobId = $auto.jobId
    hybridJobId = $hybrid.jobId
    autoPath = $auto.path
    hybridPath = $hybrid.path
    autoGainKm = [double]$autoPd.gainKm
    hybridGainKm = [double]$pd.gainKm
    gainOverAutoKm = [math]::Round(([double]$pd.gainKm - [double]$autoPd.gainKm), 1)
    operatorApplied = [bool]$pd.applied
    evaluatedCandidates = [int]$pd.evaluatedMutations
    feasibleCandidates = [int]$pd.feasibleMutations
    acceptedMutations = [int]$pd.acceptedMutations
    verdict = [string]$bsi.verdict
    improvedBestSeed = [bool]$bsi.improvedBestSeed
    pickupDropoffViolations = [int]$pd.pickupDropoffViolations
    capacityViolations = [int]$pd.capacityViolations
    lateRegression = [int]$pd.lateRegression
    coverageRegression = [int]$pd.coverageRegression
    dominancePassed = [bool]$dominance.baselineDominancePassed
  }
}

$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "pd-cross-swapstar"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  compileJava = if($SkipCompile) { "SKIPPED" } else { "PASS" }
  health = $health
  completed = $rows.Count
  operatorAppliedCount = @($rows | Where-Object { $_.operatorApplied }).Count
  improvedBestSeedCases = @($rows | Where-Object { $_.improvedBestSeed }).Count
  hybridBetterThanAutoCases = @($rows | Where-Object { $_.gainOverAutoKm -gt 0 }).Count
  hybridWorseThanAutoCases = @($rows | Where-Object { $_.gainOverAutoKm -lt 0 }).Count
  totalAutoGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.autoGainKm }) | Measure-Object -Sum).Sum, 1)
  totalHybridGainKm = [math]::Round((@($rows | ForEach-Object { [double]$_.hybridGainKm }) | Measure-Object -Sum).Sum, 1)
  safetyPass = $false
  qualityPassVsAuto = $false
  pickupDropoffViolations = (@($rows | ForEach-Object { [int]$_.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations = (@($rows | ForEach-Object { [int]$_.capacityViolations }) | Measure-Object -Sum).Sum
  lateRegression = (@($rows | ForEach-Object { [int]$_.lateRegression }) | Measure-Object -Sum).Sum
  coverageRegression = (@($rows | ForEach-Object { [int]$_.coverageRegression }) | Measure-Object -Sum).Sum
  dominanceFailures = @($rows | Where-Object { -not $_.dominancePassed }).Count
  overallPass = $false
  rows = $rows
}
$summary.safetyPass = $summary.completed -eq $Datasets.Count `
  -and $summary.operatorAppliedCount -eq $Datasets.Count `
  -and $summary.improvedBestSeedCases -ge 1 `
  -and $summary.pickupDropoffViolations -eq 0 `
  -and $summary.capacityViolations -eq 0 `
  -and $summary.lateRegression -eq 0 `
  -and $summary.coverageRegression -eq 0 `
  -and $summary.dominanceFailures -eq 0
$summary.qualityPassVsAuto = $summary.hybridWorseThanAutoCases -eq 0 -and $summary.totalHybridGainKm -ge $summary.totalAutoGainKm
$summary.overallPass = $summary.safetyPass -and $summary.qualityPassVsAuto
$summaryPath = Join-Path $out "pd-cross-swapstar-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[PD-CROSS-SWAPSTAR] summary=$summaryPath"
if(-not $summary.overallPass) { throw "PD cross/swap-star gate FAIL" }
Write-Host "[PD-CROSS-SWAPSTAR] PASS"
