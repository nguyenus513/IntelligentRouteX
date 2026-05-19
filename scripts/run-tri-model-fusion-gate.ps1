param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "wide-deadline-case"),
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C-tri-model-fusion/fusion-5case",
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
  Write-Host "[TRI-FUSION] dataset=$dataset"
  $policy = Run-Benchmark $dataset "POLICY_ONLY_PD_LNS"
  $tabular = Run-Benchmark $dataset "TABULAR_WEIGHT_075"
  $routefinder = Run-Benchmark $dataset "ROUTEFINDER_ASSISTED_PD_LNS"
  $greedrl = Run-Benchmark $dataset "GREEDRL_CONTROLLER_PD_LNS"
  $fusion = Run-Benchmark $dataset "TRI_MODEL_FUSION_PD_LNS"
  $pd = Pd $fusion
  $workers = $pd.mlWorkerProof.workers
  $bestSingle = (@((Gain $policy), (Gain $tabular), (Gain $routefinder), (Gain $greedrl)) | Measure-Object -Maximum).Maximum
  $rows += [pscustomobject]@{
    datasetId=$dataset
    policyGainKm=Gain $policy
    tabularGainKm=Gain $tabular
    routefinderGainKm=Gain $routefinder
    greedRlGainKm=Gain $greedrl
    fusionGainKm=Gain $fusion
    bestSingleModelGainKm=[double]$bestSingle
    fusionWorseThanBestSingleModel=((Gain $fusion) -lt [double]$bestSingle)
    fusionBetterThanBestSingleModel=((Gain $fusion) -gt [double]$bestSingle)
    forecastCalled=[bool]$workers.forecast.called
    tabularCalled=[bool]$workers.tabular.called
    routefinderCalled=[bool]$workers.routefinder.called
    greedRlCalled=[bool]$workers.greedrl.called
    pickupDropoffViolations=[int]$pd.pickupDropoffViolations
    capacityViolations=[int]$pd.capacityViolations
    lateRegression=[int]$pd.lateRegression
    coverageRegression=[int]$pd.coverageRegression
    dominancePassed=[bool]$fusion.diagnostics.baselineDominanceGuard.baselineDominancePassed
  }
}
$summary = [pscustomobject]@{
  version="v0.9.10-C-tri-model-fusion"; gate="tri-model-fusion"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}; health=$health
  completed=$rows.Count; expected=$Datasets.Count
  forecastCalledCases=@($rows | Where-Object forecastCalled).Count
  tabularCalledCases=@($rows | Where-Object tabularCalled).Count
  routefinderCalledCases=@($rows | Where-Object routefinderCalled).Count
  greedRlCalledCases=@($rows | Where-Object greedRlCalled).Count
  fusionWorseThanBestSingleModelCases=@($rows | Where-Object fusionWorseThanBestSingleModel).Count
  fusionBetterThanBestSingleModelCases=@($rows | Where-Object fusionBetterThanBestSingleModel).Count
  totalFusionGainKm=[math]::Round((@($rows | ForEach-Object fusionGainKm) | Measure-Object -Sum).Sum, 1)
  totalBestSingleModelGainKm=[math]::Round((@($rows | ForEach-Object bestSingleModelGainKm) | Measure-Object -Sum).Sum, 1)
  pickupDropoffViolations=(@($rows | ForEach-Object pickupDropoffViolations) | Measure-Object -Sum).Sum
  capacityViolations=(@($rows | ForEach-Object capacityViolations) | Measure-Object -Sum).Sum
  lateRegression=(@($rows | ForEach-Object lateRegression) | Measure-Object -Sum).Sum
  coverageRegression=(@($rows | ForEach-Object coverageRegression) | Measure-Object -Sum).Sum
  dominanceFailures=@($rows | Where-Object { -not $_.dominancePassed }).Count
  verdict="TRI_MODEL_FUSION_SAFE_BUT_NOT_BETTER"
  overallPass=$false
  rows=$rows
}
$summary.overallPass = $summary.completed -eq $summary.expected -and $summary.forecastCalledCases -eq 0 -and $summary.tabularCalledCases -eq $summary.expected -and $summary.routefinderCalledCases -eq $summary.expected -and $summary.greedRlCalledCases -eq $summary.expected -and $summary.fusionWorseThanBestSingleModelCases -eq 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.coverageRegression -eq 0 -and $summary.dominanceFailures -eq 0
if($summary.overallPass -and $summary.fusionBetterThanBestSingleModelCases -ge 1) { $summary.verdict = "TRI_MODEL_FUSION_GAIN_PROVEN" }
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "tri-model-fusion-summary.json")
Write-Host "[TRI-FUSION] summary=$(Join-Path $out 'tri-model-fusion-summary.json')"
if(-not $summary.overallPass) { throw "Tri-model fusion gate FAIL verdict=$($summary.verdict)" }
Write-Host "[TRI-FUSION] PASS"
