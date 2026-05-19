param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C1-tri-model-20case/fusion-20case",
  [switch]$SkipCompile,
  [int]$TimeoutSec = 1200
)

$ErrorActionPreference = "Stop"

$datasets = @(
  "raw-s", "raw-m", "random-spread", "driver-scarcity-case", "tight-deadline-case",
  "wide-deadline-case", "driver-imbalanced-case", "many-orders-few-drivers", "few-orders-many-drivers",
  "opposite-direction-dropoffs", "clustered-pickups-random-dropoffs", "random-pickups-clustered-dropoffs",
  "long-tail-distance", "tight-capacity", "high-priority-orders", "active-route-insertion",
  "driver-location-shift", "deferred-order-aging", "rescue-like-rebalance", "high-density-lunch-rush"
)

$gate = Join-Path $PSScriptRoot "run-tri-model-fusion-gate.ps1"
$gateArgs = @{
  BaseUrl = $BaseUrl
  Datasets = $datasets
  OutputDir = $OutDir
  TimeoutSec = $TimeoutSec
}
if($SkipCompile) { $gateArgs.SkipCompile = $true }

& $gate @gateArgs

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$summaryPath = Join-Path (Join-Path $root $OutDir) "tri-model-fusion-summary.json"
$summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
$summary | Add-Member -Force -NotePropertyName gate -NotePropertyValue "tri-model-fusion-20case"
$summary | Add-Member -Force -NotePropertyName version -NotePropertyValue "v0.9.10-C1-tri-model-20case"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath

if($summary.completed -ne 20 -or -not $summary.overallPass) {
  throw "Tri-model fusion 20-case gate FAIL completed=$($summary.completed) overallPass=$($summary.overallPass)"
}
if($summary.fusionBetterThanBestSingleModelCases -lt 1 -or $summary.totalFusionGainKm -lt $summary.totalBestSingleModelGainKm) {
  throw "Tri-model fusion 20-case quality FAIL betterCases=$($summary.fusionBetterThanBestSingleModelCases) fusion=$($summary.totalFusionGainKm) bestSingle=$($summary.totalBestSingleModelGainKm)"
}

Write-Host "[TRI-FUSION-20] PASS summary=$summaryPath"
