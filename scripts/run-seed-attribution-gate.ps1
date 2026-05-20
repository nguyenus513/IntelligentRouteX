param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "wide-deadline-case", "driver-scarcity-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-ml-best-seed-improver/seed-attribution",
  [int]$TimeoutSec = 600
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) {
  Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 20) -TimeoutSec $timeout
}
function Require-Field($object, [string]$name, [string]$dataset) {
  if($null -eq $object -or -not ($object.PSObject.Properties.Name -contains $name)) { throw "missing $name in bestSeedImprovement dataset=$dataset" }
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$rows = @()
foreach($dataset in $Datasets) {
  Write-Host "[SEED-ATTR] dataset=$dataset"
  $request = @{
    datasetId = $dataset
    mode = "QUALITY_BENCHMARK"
    solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
    adaptiveMlPolicyMode = "QUALITY_SEEKING"
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
  if($null -eq $result) { throw "timeout dataset=$dataset job=$($job.jobId)" }
  $rawPath = Join-Path $out "$dataset-attribution-result.json"
  $result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $rawPath
  $bsi = $result.diagnostics.bestSeedImprovement
  foreach($field in @("baseBestSeedSource", "baseBestSeedKm", "baseBestSeedAssigned", "baseBestSeedLate", "finalSeedSource", "finalKm", "finalAssigned", "finalLate", "distanceGainOverBestSeedKm", "improvedBestSeed", "verdict")) {
    Require-Field $bsi $field $dataset
  }
  $rows += [pscustomobject]@{
    datasetId = $dataset
    jobId = $job.jobId
    baseBestSeedSource = $bsi.baseBestSeedSource
    baseBestSeedKm = $bsi.baseBestSeedKm
    finalSeedSource = $bsi.finalSeedSource
    finalKm = $bsi.finalKm
    distanceGainOverBestSeedKm = $bsi.distanceGainOverBestSeedKm
    improvedBestSeed = $bsi.improvedBestSeed
    verdict = $bsi.verdict
    path = $rawPath
  }
}

$allowed = @("ML_BEST_SEED_DISTANCE_IMPROVED", "ML_BEST_SEED_OBJECTIVE_IMPROVED", "HEURISTIC_BEST_SEED_DISTANCE_IMPROVED", "BEST_SEED_PRESERVED", "WIN_BY_OTHER_SEED_NOT_COUNTED", "TIE_WITH_BEST_SEED", "ROLLBACK_TO_BEST_SEED", "NO_SEED_IMPROVEMENT")
$invalid = @($rows | Where-Object { $_.verdict -notin $allowed })
$summary = [pscustomobject]@{
  version = "v0.9.10-ml-guided-pd-lns-seed-improver"
  gate = "seed-attribution"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  health = $health
  overallPass = ($invalid.Count -eq 0)
  improvedBestSeedCases = @($rows | Where-Object { $_.improvedBestSeed -eq $true }).Count
  totalDistanceGainOverBestSeedKm = [math]::Round((@($rows | ForEach-Object { [double]$_.distanceGainOverBestSeedKm }) | Measure-Object -Sum).Sum, 1)
  rows = $rows
}
$summaryPath = Join-Path $out "seed-attribution-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[SEED-ATTR] summary=$summaryPath"
if(-not $summary.overallPass) { throw "Seed attribution gate FAIL" }
Write-Host "[SEED-ATTR] PASS"
