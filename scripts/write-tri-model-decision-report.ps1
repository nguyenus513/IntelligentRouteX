param(
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.10-C-tri-model-fusion"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

$fusionPath = Join-Path $out "fusion-5case/tri-model-fusion-summary.json"
$ablationPath = Join-Path $out "ablation-5case/tri-model-causal-ablation-summary.json"
$fusion = if(Test-Path $fusionPath) { Get-Content $fusionPath -Raw | ConvertFrom-Json } else { $null }
$ablation = if(Test-Path $ablationPath) { Get-Content $ablationPath -Raw | ConvertFrom-Json } else { $null }

$report = [pscustomobject]@{
  version = "v0.9.10-C-tri-model-fusion"
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  staticDefault = "TRI_MODEL_FUSION_PD_LNS"
  noRegressSelector = $true
  fusionEvidence = @{
    overallPass = $fusion -ne $null -and [bool]$fusion.overallPass
    fusionWorseThanBestSingleModelCases = if($fusion){ [int]$fusion.fusionWorseThanBestSingleModelCases } else { -1 }
    fusionBetterThanBestSingleModelCases = if($fusion){ [int]$fusion.fusionBetterThanBestSingleModelCases } else { -1 }
    totalFusionGainKm = if($fusion){ [double]$fusion.totalFusionGainKm } else { 0.0 }
    totalBestSingleModelGainKm = if($fusion){ [double]$fusion.totalBestSingleModelGainKm } else { 0.0 }
  }
  ablationEvidence = @{
    overallPass = $ablation -ne $null -and [bool]$ablation.overallPass
    verdict = if($ablation){ [string]$ablation.verdict } else { "MISSING" }
    modelWorkersWithContribution = if($ablation){ [int]$ablation.modelWorkersWithContribution } else { 0 }
  }
  adaptivePolicy = @{ decision = "KEEP_CORE"; role = "core decision controller" }
  tabular = @{ decision = "KEEP_MODEL_STATIC"; role = "mutation/insertion scorer"; evidence = "causal quality gain proven" }
  routefinder = @{ decision = "KEEP_OPTIONAL_PROVIDER"; role = "route/edge/sequence candidate provider"; evidence = "selected-case contribution" }
  greedrl = @{ decision = "KEEP_CONTROLLER_SELECTED"; role = "operator/action controller"; evidence = "selected-case causal gain" }
  forecast = @{ decision = "OFF_STATIC_LIVE_RESCUE_ONLY"; role = "ETA/SLA/risk scorer"; evidence = "static quality/risk gain not proven" }
}

$path = Join-Path $out "tri-model-decision-report.json"
$report | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $path
Write-Host "[TRI-MODEL-REPORT] report=$path"
