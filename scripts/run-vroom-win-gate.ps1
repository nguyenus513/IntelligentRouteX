param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "wide-deadline-case", "driver-imbalanced-case"),
  [int]$DatasetTimeoutSeconds = 360,
  [string]$OutputDir = "artifacts/test-reports/vroom-win-gate",
  [switch]$RequireVroomImprovedWin
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Verdict($irxAssigned, $irxInput, $irxKm, $irxLate, $vroomAssigned, $vroomInput, $vroomKm, $vroomLate) {
  if ($null -eq $vroomKm -or [double]$vroomKm -le 0) { return "NOT_AVAILABLE" }
  $safeIrxInput = [math]::Max(1, [int]$irxInput)
  $safeVroomInput = [math]::Max(1, [int]$vroomInput)
  $irxCoverage = [double]$irxAssigned / [double]$safeIrxInput
  $vroomCoverage = [double]$vroomAssigned / [double]$safeVroomInput
  if ($irxCoverage -gt $vroomCoverage) { return "WIN" }
  if ($irxCoverage -lt $vroomCoverage) { return "LOSS" }
  if ([int]$irxLate -lt [int]$vroomLate) { return "WIN" }
  if ([int]$irxLate -gt [int]$vroomLate) { return "LOSS" }
  if ([double]$irxKm -lt [double]$vroomKm) { return "WIN" }
  if ([double]$irxKm -eq [double]$vroomKm) { return "TIE" }
  return "LOSS"
}

$rows = @()
$artifacts = @()
foreach ($dataset in $Datasets) {
  $body = @{ datasetId = $dataset; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
  $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec 180
  $artifact = Join-Path $OutputDir "vroom-win-gate-$dataset-$($job.jobId).json"
  $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
  $artifacts += $artifact
  $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  $vroom = $result.diagnostics.solverResults | Where-Object solverName -eq "VROOM" | Select-Object -First 1
  $externalDominance = $result.diagnostics.externalSeedDominance
  $verdict = Verdict $hybrid.assignedOrderCount $hybrid.inputOrderCount $hybrid.totalDistanceKm $hybrid.lateOrderCount $vroom.assignedOrderCount $vroom.inputOrderCount $vroom.totalDistanceKm $vroom.lateOrderCount
  $rows += [pscustomobject]@{
    datasetId = $dataset
    jobId = $job.jobId
    runId = $result.runId
    irxKm = [double]$hybrid.totalDistanceKm
    irxLate = [int]$hybrid.lateOrderCount
    irxAssigned = [int]$hybrid.assignedOrderCount
    irxInput = [int]$hybrid.inputOrderCount
    vroomKm = [double]$vroom.totalDistanceKm
    vroomLate = [int]$vroom.lateOrderCount
    vroomAssigned = [int]$vroom.assignedOrderCount
    vroomInput = [int]$vroom.inputOrderCount
    vroomStatus = $vroom.status
    vsVroomObjective = $verdict
    externalDominancePassed = [bool]$externalDominance.passed
    rollbackApplied = [bool]$externalDominance.rollbackApplied
    finalSeedSource = $externalDominance.finalSeedSource
    selectedSeedSource = $hybrid.reason
    finalSolverInvariant = $hybrid.solverName -eq "IRX ML-Fused Hybrid"
    passNoLoss = ($verdict -eq "WIN" -or $verdict -eq "TIE") -and [bool]$externalDominance.passed
    passVroomImprovedWin = ($verdict -eq "WIN") -and ($externalDominance.finalSeedSource -eq "VROOM_SEED_IMPROVED")
  }
}

$wins = @($rows | Where-Object { $_.vsVroomObjective -eq "WIN" }).Count
$ties = @($rows | Where-Object { $_.vsVroomObjective -eq "TIE" }).Count
$losses = @($rows | Where-Object { $_.vsVroomObjective -eq "LOSS" }).Count
$notAvailable = @($rows | Where-Object { $_.vsVroomObjective -eq "NOT_AVAILABLE" }).Count
$strictFailures = @($rows | Where-Object { -not $_.passVroomImprovedWin }).Count
$noLossPass = ($rows.Count -gt 0 -and $losses -eq 0 -and $notAvailable -eq 0 -and (@($rows | Where-Object { -not $_.externalDominancePassed }).Count -eq 0))
$strictPass = $noLossPass -and $strictFailures -eq 0
$summary = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = if ($RequireVroomImprovedWin) { $strictPass } else { $noLossPass }
  noLossPass = $noLossPass
  strictVroomImprovedPass = $strictPass
  strictMode = [bool]$RequireVroomImprovedWin
  status = if ($strictPass) { "VROOM_IMPROVED_WIN" } elseif ($losses -eq 0 -and $wins -gt 0) { "WIN_WITH_NO_LOSS" } elseif ($losses -eq 0) { "NO_LOSS_NOT_WIN" } else { "LOSS" }
  total = $rows.Count
  wins = $wins
  ties = $ties
  losses = $losses
  notAvailable = $notAvailable
  vroomImprovedWins = @($rows | Where-Object { $_.passVroomImprovedWin }).Count
  strictFailures = $strictFailures
  rows = $rows
  artifacts = $artifacts
}

$summaryPath = Join-Path $OutputDir "vroom-win-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.pass) { exit 1 }
