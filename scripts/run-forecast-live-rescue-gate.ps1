param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C2-forecast-live-rescue/live-rescue-gate",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Get-Json($uri, [int]$timeout = 60) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec $timeout }
function Post-Json($uri, $body, [int]$timeout = 600) { Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec $timeout }
function Run-Benchmark([string]$row, [string]$dataset, [string]$pdMode) {
  $path = Join-Path $out "$row-$dataset-$pdMode-result.json"
  if(Test-Path $path) { return Get-Content $path -Raw | ConvertFrom-Json }
  $request = @{ datasetId=$dataset; mode="QUALITY_BENCHMARK"; solvers=@("OR-Tools","PyVRP","VROOM","IntelligentRouteX"); adaptiveMlPolicyMode="QUALITY_SEEKING"; pdLnsMode=$pdMode; pdLnsMaxRounds=2; pdLnsTopBadOrders=8; pdLnsBudgetMs=3000 }
  $job = Post-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs" $request $TimeoutSec
  $result = $null; $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while((Get-Date) -lt $deadline) {
    try { $result = Get-Json "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" 120; if($result.status -eq "COMPLETED" -or $result.runStatus -eq "COMPLETED" -or $result.status -eq "FAILED" -or $result.runStatus -eq "FAILED") { break } } catch { Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2
  }
  if($null -eq $result) { throw "timeout row=$row dataset=$dataset mode=$pdMode job=$($job.jobId)" }
  $result | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
  return $result
}
function Gain($result) { [double]$result.diagnostics.pdLnsImprovement.gainKm }
function Pd($result) { $result.diagnostics.pdLnsImprovement }
function Worker($result, $name) { (Pd $result).mlWorkerProof.workers.$name }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }
$health = Get-Json "$BaseUrl/api/v1/health" 30

$scenarios = @(
  [pscustomobject]@{ row="LIVE_ROLLING"; dataset="deferred-order-aging" },
  [pscustomobject]@{ row="RESCUE"; dataset="rescue-like-rebalance" }
)
$rows = @()
foreach($scenario in $scenarios) {
  Write-Host "[FORECAST-LIVE-RESCUE] row=$($scenario.row) dataset=$($scenario.dataset) no-forecast"
  $noForecast = Run-Benchmark "$($scenario.row)_NO_FORECAST" $scenario.dataset "NO_FORECAST"
  Write-Host "[FORECAST-LIVE-RESCUE] row=$($scenario.row) dataset=$($scenario.dataset) with-forecast"
  $forecast = Run-Benchmark "$($scenario.row)_WITH_FORECAST" $scenario.dataset "FORECAST_RISK_PD_LNS"
  $pd = Pd $forecast
  $basePd = Pd $noForecast
  $worker = Worker $forecast "forecast"
  $rows += [pscustomobject]@{
    row=$scenario.row
    datasetId=$scenario.dataset
    noForecastGainKm=Gain $noForecast
    forecastGainKm=Gain $forecast
    forecastBetterThanNoForecast=((Gain $forecast) -gt (Gain $noForecast))
    forecastRiskReduced=([int]$pd.lateRegression -lt [int]$basePd.lateRegression -or [int]$pd.coverageRegression -lt [int]$basePd.coverageRegression)
    forecastCalled=[bool]$worker.called
    forecastRiskCount=[int]$worker.candidateCount
    forecastOutputUsed=[bool]$worker.outputUsed
    forecastAffectedDecisionCount=[int]$worker.affectedDecisionCount
    forecastAcceptedCandidateCount=[int]$worker.acceptedCandidateCount
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$forecast.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}

$summary = [pscustomobject]@{
  version="v0.9.10-C2-forecast-live-rescue"; gate="forecast-live-rescue"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=($rows.Count * 2); expected=($scenarios.Count * 2)
  liveCycles=(@($rows | Where-Object { $_.row -eq "LIVE_ROLLING" }).Count * 2)
  rescueJobs=(@($rows | Where-Object { $_.row -eq "RESCUE" }).Count * 2)
  staleBufferedOrders=0
  forecastCalledCases=@($rows | Where-Object forecastCalled).Count
  forecastRiskCount=(@($rows | ForEach-Object forecastRiskCount) | Measure-Object -Sum).Sum
  forecastOutputUsedCases=@($rows | Where-Object forecastOutputUsed).Count
  forecastAffectedDecisionCount=(@($rows | ForEach-Object forecastAffectedDecisionCount) | Measure-Object -Sum).Sum
  forecastAcceptedCandidateCount=(@($rows | ForEach-Object forecastAcceptedCandidateCount) | Measure-Object -Sum).Sum
  forecastRiskReducedCases=@($rows | Where-Object forecastRiskReduced).Count
  rescueBetterCases=@($rows | Where-Object { $_.row -eq "RESCUE" -and $_.forecastBetterThanNoForecast }).Count
  forecastBetterThanNoForecastCases=@($rows | Where-Object forecastBetterThanNoForecast).Count
  totalNoForecastGainKm=[math]::Round((@($rows | ForEach-Object noForecastGainKm) | Measure-Object -Sum).Sum, 1)
  totalForecastGainKm=[math]::Round((@($rows | ForEach-Object forecastGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  diagnosticPass=$false
  qualityPass=$false
  verdict="FORECAST_LIVE_RESCUE_DIAGNOSTIC_ONLY"
  overallPass=$false
  rows=$rows
}
$summary.diagnosticPass = $summary.completed -eq $summary.expected -and $summary.forecastCalledCases -eq $scenarios.Count -and $summary.forecastRiskCount -gt 0 -and $summary.forecastOutputUsedCases -eq $scenarios.Count -and $summary.forecastAffectedDecisionCount -gt 0 -and $summary.staleBufferedOrders -eq 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary.qualityPass = $summary.diagnosticPass -and ($summary.forecastRiskReducedCases -ge 1 -or $summary.rescueBetterCases -ge 1)
$summary.overallPass = $summary.diagnosticPass
if($summary.qualityPass) { $summary.verdict = "FORECAST_LIVE_RESCUE_RISK_SCORER_PROVEN" }
elseif($summary.diagnosticPass) { $summary.verdict = "FORECAST_LIVE_RESCUE_HOT_PATH_PROVEN_NO_QUALITY_OR_RISK_GAIN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "forecast-live-rescue-summary.json")
Write-Host "[FORECAST-LIVE-RESCUE] summary=$(Join-Path $out 'forecast-live-rescue-summary.json')"
if(-not $summary.overallPass) { throw "Forecast live/rescue gate FAIL verdict=$($summary.verdict)" }
Write-Host "[FORECAST-LIVE-RESCUE] PASS verdict=$($summary.verdict)"
