param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OsrmBaseUrl = "http://127.0.0.1:5001",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "wide-deadline-case", "driver-scarcity-case"),
  [string]$OutDir = "artifacts/test-reports/v0.9.9-core-solver-benchmark",
  [int]$TimeoutSec = 600
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function NowIso { (Get-Date).ToUniversalTime().ToString("o") }
function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) {
  Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 20) -TimeoutSec $timeout
}
function ObjectiveKey($r) {
  if($null -eq $r -or $r.status -ne "COMPLETED") { return @(1, 999999, 999999, 999999) }
  $unassigned = [int]$r.inputOrderCount - [int]$r.assignedOrderCount
  return @(0, $unassigned, [int]$r.lateOrderCount, [double]$r.totalDistanceKm)
}
function Compare-Objective($candidate, $baseline) {
  $a = ObjectiveKey $candidate; $b = ObjectiveKey $baseline
  for($i=0; $i -lt $a.Count; $i++) {
    if($a[$i] -lt $b[$i]) { return "WIN" }
    if($a[$i] -gt $b[$i]) { return "LOSS" }
  }
  return "TIE"
}

$health = Get-Json "$BaseUrl/api/v1/health" 30
$osrmProbe = Get-Json "$OsrmBaseUrl/route/v1/driving/106.7009,10.7769;106.7042,10.7731?overview=false" 30
if($osrmProbe.code -ne "Ok") { throw "OSRM probe failed: $($osrmProbe.code)" }

$runs = @()
foreach($dataset in $Datasets) {
  Write-Host "[IRX-BENCH] dataset=$dataset"
  $request = @{
    datasetId = $dataset
    mode = "QUALITY_BENCHMARK"
    solvers = @("OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX")
    adaptiveMlPolicyMode = "QUALITY_SEEKING"
  }
  $job = Post-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs" $request $TimeoutSec
  $jobId = $job.jobId
  $result = $null
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while((Get-Date) -lt $deadline) {
    try {
      $result = Get-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$jobId/result" 120
      if($result.status -eq "COMPLETED" -or $result.runStatus -eq "COMPLETED") { break }
      if($result.status -eq "FAILED" -or $result.runStatus -eq "FAILED") { break }
    } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2
  }
  if($null -eq $result) { throw "Benchmark timeout: $dataset job=$jobId" }
  $rawPath = Join-Path $out "$dataset-result.json"
  $result | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 $rawPath

  $solverResults = @($result.diagnostics.solverResults)
  $hybrid = $solverResults | Where-Object { $_.solverName -eq "IRX ML-Fused Hybrid" } | Select-Object -First 1
  $baselines = $solverResults | Where-Object { $_.solverName -in @("OR-Tools", "PyVRP", "VROOM") }
  $comparisons = @($baselines | ForEach-Object {
    [pscustomobject]@{
      baseline = $_.solverName
      verdict = Compare-Objective $hybrid $_
      baselineStatus = $_.status
      baselineDistanceKm = $_.totalDistanceKm
      baselineLate = $_.lateOrderCount
      baselineAssigned = $_.assignedOrderCount
      inputOrders = $_.inputOrderCount
    }
  })
  $matrix = $result.diagnostics.matrixSnapshot
  $runs += [pscustomobject]@{
    datasetId = $dataset
    jobId = $jobId
    matrixProvider = $matrix.provider
    matrixFallbackApplied = $matrix.fallbackApplied
    solverResults = $solverResults | Select-Object solverName,status,totalDistanceKm,lateOrderCount,assignedOrderCount,inputOrderCount,reason
    hybrid = $hybrid | Select-Object solverName,status,totalDistanceKm,lateOrderCount,assignedOrderCount,inputOrderCount,reason
    comparisons = $comparisons
    resultPath = $rawPath
  }
}

$matrixPass = @($runs | Where-Object { $_.matrixProvider -ne "osrm-table" -or $_.matrixFallbackApplied -ne $false }).Count -eq 0
$completedPass = @($runs | ForEach-Object { $_.solverResults } | Where-Object { $_.solverName -in @("OR-Tools", "PyVRP", "VROOM", "IRX ML-Fused Hybrid") -and $_.status -ne "COMPLETED" }).Count -eq 0
$summary = [pscustomobject]@{
  version = "v0.9.9-core-solver-benchmark-osrm"
  generatedAt = NowIso
  baseUrl = $BaseUrl
  health = $health
  osrm = @{ baseUrl = $OsrmBaseUrl; probeCode = $osrmProbe.code }
  datasets = $Datasets
  matrixOsrmPass = $matrixPass
  solversCompletedPass = $completedPass
  overallPass = ($matrixPass -and $completedPass)
  runs = $runs
}
$summaryPath = Join-Path $out "core-solver-benchmark-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "[IRX-BENCH] summary=$summaryPath"
if(-not $summary.overallPass) { throw "Core solver benchmark gate FAIL" }
Write-Host "[IRX-BENCH] PASS"
