param(
  [string]$BaseUrl = "http://localhost:18116",
  [string[]]$Datasets = @("raw-s"),
  [string]$AblationDir = "artifacts/test-reports/ml-evidence/ablation-restart",
  [string]$OutputDir = "artifacts/test-reports/ml-evidence/ml-guided-improvement"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Read-LatestJson($dir, $filter) {
  $file = Get-ChildItem -Path $dir -Recurse -Filter $filter -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($null -eq $file) { return $null }
  return Get-Content $file.FullName -Raw | ConvertFrom-Json
}

function CoverageTotal($coverage) {
  if ($null -eq $coverage) { return 0 }
  if ($coverage -notmatch '^(\d+)/(\d+)$') { return 0 }
  return [int]$Matches[2]
}

function CoverageAssigned($coverage) {
  if ($null -eq $coverage) { return 0 }
  if ($coverage -notmatch '^(\d+)/(\d+)$') { return 0 }
  return [int]$Matches[1]
}

function BestFullSeed($artifact) {
  $sources = $artifact.diagnostics.seedSourceAudit.sources
  if ($null -eq $sources) { return $null }
  $candidates = @()
  foreach ($property in $sources.PSObject.Properties) {
    $seed = $property.Value
    $assigned = CoverageAssigned $seed.coverage
    $total = CoverageTotal $seed.coverage
    if ($seed.completed -and $seed.feasible -and $assigned -eq $total -and $total -gt 0) {
      $candidates += [pscustomobject]@{
        source = $property.Name
        distanceKm = [double]$seed.distanceKmExact
        lateCount = [int]$seed.lateCount
        coverage = [string]$seed.coverage
        capacityViolations = [int]$seed.capacityViolations
        pickupDropoffViolations = [int]$seed.pickupDropoffViolations
        runtimeMs = [int64]$seed.runtimeMs
      }
    }
  }
  return $candidates | Sort-Object lateCount, distanceKm | Select-Object -First 1
}

function RowFromAblation($summary, $mode, $label) {
  $row = $summary.rows | Where-Object mode -eq $mode | Select-Object -First 1
  if ($null -eq $row) { return $null }
  return [pscustomobject]@{
    row = $label
    mode = $mode
    source = [string]$row.selectedFinalSource
    distanceKm = [double]$row.distanceKm
    lateCount = [int]$row.lateCount
    coverage = [string]$row.coverage
    runtimeMs = [int64]$row.runtimeMs
    artifact = [string]$row.artifact
  }
}

$ablation = Read-LatestJson $AblationDir "ml-ablation-restart-summary.json"
if ($null -eq $ablation) {
  throw "missing-restart-ablation-summary:$AblationDir. Run scripts/run-ml-ablation-restart-loop.ps1 first."
}

$fullRow = $ablation.rows | Where-Object mode -eq "FULL_ML" | Select-Object -First 1
if ($null -eq $fullRow -or -not (Test-Path $fullRow.artifact)) {
  throw "missing-full-ml-artifact-in-ablation-summary"
}
$fullArtifact = Get-Content $fullRow.artifact -Raw | ConvertFrom-Json
$best = BestFullSeed $fullArtifact
if ($null -eq $best) { throw "missing-best-full-seed-in-artifact:$($fullRow.artifact)" }

$rows = @()
$rows += [pscustomobject]@{
  row = "BEST_FULL_SEED_ONLY"
  mode = "SEED_ONLY"
  source = $best.source
  distanceKm = $best.distanceKm
  lateCount = $best.lateCount
  coverage = $best.coverage
  runtimeMs = $best.runtimeMs
  artifact = $fullRow.artifact
}
$rows += RowFromAblation $ablation "NO_ML_ALL" "HEURISTIC_IMPROVER_NO_ML"
$rows += RowFromAblation $ablation "FULL_ML" "ML_GUIDED_IMPROVER"
$rows += RowFromAblation $ablation "NO_TABULAR" "ML_GUIDED_NO_TABULAR"
$rows += RowFromAblation $ablation "NO_GREEDRL" "ML_GUIDED_NO_GREEDRL"
$rows += RowFromAblation $ablation "NO_FORECAST" "ML_GUIDED_NO_FORECAST"
$rows += RowFromAblation $ablation "NO_ROUTEFINDER" "ML_GUIDED_NO_ROUTEFINDER"
$rows = @($rows | Where-Object { $null -ne $_ })

$ml = $rows | Where-Object row -eq "ML_GUIDED_IMPROVER" | Select-Object -First 1
$heuristic = $rows | Where-Object row -eq "HEURISTIC_IMPROVER_NO_ML" | Select-Object -First 1
$bestSeed = $rows | Where-Object row -eq "BEST_FULL_SEED_ONLY" | Select-Object -First 1

$coverageUnchanged = (CoverageAssigned $ml.coverage) -eq (CoverageAssigned $bestSeed.coverage) -and (CoverageTotal $ml.coverage) -eq (CoverageTotal $bestSeed.coverage)
$lateNotWorse = [int]$ml.lateCount -le [int]$bestSeed.lateCount
$capacityValid = [int]$best.capacityViolations -eq 0
$pickupDropoffValid = [int]$best.pickupDropoffViolations -eq 0
$improvesBestFullSeed = ([double]$ml.distanceKm -lt [double]$bestSeed.distanceKm) -and $lateNotWorse -and $coverageUnchanged
$notWorseThanHeuristic = if ($heuristic) { ([double]$ml.distanceKm -le [double]$heuristic.distanceKm) -and ([int]$ml.lateCount -le [int]$heuristic.lateCount) } else { $false }
$strictMlGainVsHeuristic = if ($heuristic) { ([double]$ml.distanceKm -lt [double]$heuristic.distanceKm) -or ([int]$ml.lateCount -lt [int]$heuristic.lateCount) } else { $false }

$summary = [pscustomobject]@{
  schemaVersion = "ml-guided-improvement-gate/v1"
  createdAt = (Get-Date).ToString("o")
  baseUrl = $BaseUrl
  datasets = $Datasets
  pass = $improvesBestFullSeed -and $notWorseThanHeuristic -and $coverageUnchanged -and $lateNotWorse -and $capacityValid -and $pickupDropoffValid
  honestStatus = if ($strictMlGainVsHeuristic) { "ML_OPTIMIZATION_CONTRIBUTION_PROVEN_VS_HEURISTIC" } elseif ($improvesBestFullSeed -and $notWorseThanHeuristic) { "BEST_SEED_IMPROVED_BUT_ML_NOT_STRICTLY_BETTER_THAN_HEURISTIC" } else { "ML_OPTIMIZATION_CONTRIBUTION_NOT_PROVEN" }
  passChecks = [pscustomobject]@{
    mlGuidedImprovesBestFullSeed = $improvesBestFullSeed
    mlGuidedNotWorseThanHeuristic = $notWorseThanHeuristic
    mlGuidedStrictGainVsHeuristic = $strictMlGainVsHeuristic
    coverageUnchanged = $coverageUnchanged
    lateNotWorse = $lateNotWorse
    capacityValid = $capacityValid
    pickupDropoffValid = $pickupDropoffValid
  }
  attribution = [pscustomobject]@{
    bestFullSeedSource = $bestSeed.source
    mlGuidedFinalSource = $ml.source
    heuristicFinalSource = if ($heuristic) { $heuristic.source } else { "MISSING" }
    deltaMlVsBestSeedKm = [math]::Round(([double]$ml.distanceKm - [double]$bestSeed.distanceKm), 3)
    deltaMlVsHeuristicKm = if ($heuristic) { [math]::Round(([double]$ml.distanceKm - [double]$heuristic.distanceKm), 3) } else { $null }
  }
  rows = $rows
  sourceAblationSummary = (Resolve-Path (Join-Path $AblationDir "ml-ablation-restart-summary.json") -ErrorAction SilentlyContinue).Path
}

$summaryPath = Join-Path $OutputDir "ml-guided-improvement-summary.json"
$summary | ConvertTo-Json -Depth 30 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
