param(
  [string]$OutputDir = "artifacts/test-reports/official-solomon-lilim-benchmark",
  [string]$Tier = "fast",
  [string]$TimeLimit = "1s",
  [string]$PythonExe = "py",
  [string]$PythonVersionArg = "-3"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$scriptArgs = @()
if ($PythonVersionArg -ne "") { $scriptArgs += $PythonVersionArg }
$scriptArgs += @(
  "scripts/run_phase15_large_benchmark.py",
  "--tier", $Tier,
  "--data-source", "official",
  "--solvers", "our-dispatch-v2,ortools-baseline,pyvrp-baseline",
  "--time-limit", $TimeLimit,
  "--output-dir", $OutputDir
)

& $PythonExe @scriptArgs | Out-Host
if ($LASTEXITCODE -ne 0) { throw "official Solomon/LiLim benchmark runner failed" }

$resultPath = Join-Path $OutputDir "phase15_large_benchmark_results.json"
$payload = Get-Content -Raw $resultPath | ConvertFrom-Json
$rows = @($payload.results)

$irxRows = @($rows | Where-Object { $_.solver -eq "our-dispatch-v2" })
$ortRows = @($rows | Where-Object { $_.solver -eq "ortools-baseline" })
$pyvrpRows = @($rows | Where-Object { $_.solver -eq "pyvrp-baseline" })

$irxFeasible = @($irxRows | Where-Object { $_.feasible -eq $true }).Count
$ortFeasible = @($ortRows | Where-Object { $_.feasible -eq $true }).Count
$pyvrpFeasible = @($pyvrpRows | Where-Object { $_.feasible -eq $true }).Count
$pyvrpEvidenceGap = @($pyvrpRows | Where-Object { $_.verdict -eq "EVIDENCE_GAP" }).Count

$wins = 0; $ties = 0; $losses = 0
$compareRows = @()
foreach ($irx in $irxRows) {
  $ort = $ortRows | Where-Object { $_.suite -eq $irx.suite -and $_.instance -eq $irx.instance } | Select-Object -First 1
  if ($null -eq $ort -or -not $irx.feasible -or -not $ort.feasible) { continue }
  $vehicleDelta = [int]$irx.vehicleCount - [int]$ort.vehicleCount
  $distanceDelta = [double]$irx.totalDistance - [double]$ort.totalDistance
  $verdict = "TIE"
  if ($vehicleDelta -lt 0 -or ($vehicleDelta -eq 0 -and $distanceDelta -lt -0.01)) { $verdict = "WIN"; $wins++ }
  elseif ($vehicleDelta -gt 0 -or ($vehicleDelta -eq 0 -and $distanceDelta -gt 0.01)) { $verdict = "LOSS"; $losses++ }
  else { $ties++ }
  $compareRows += [pscustomobject]@{
    suite = $irx.suite
    instance = $irx.instance
    irxVehicleCount = $irx.vehicleCount
    ortoolsVehicleCount = $ort.vehicleCount
    irxDistance = [Math]::Round([double]$irx.totalDistance, 3)
    ortoolsDistance = [Math]::Round([double]$ort.totalDistance, 3)
    distanceDelta = [Math]::Round($distanceDelta, 3)
    verdict = $verdict
    irxResult = $irx.verdict
    ortoolsResult = $ort.verdict
  }
}

function Get-IntOrZero($value) {
  if ($null -eq $value) { return 0 }
  return [int]$value
}

$hardViolationRows = @($irxRows | Where-Object {
  (Get-IntOrZero $_.capacityViolationCount) -gt 0 -or
  (Get-IntOrZero $_.timeWindowViolationCount) -gt 0 -or
  (Get-IntOrZero $_.pickupBeforeDropoffViolationCount) -gt 0 -or
  (Get-IntOrZero $_.vehicleLimitViolationCount) -gt 0
})

$summary = [ordered]@{
  version = "official-solomon-lilim-benchmark"
  gate = "official-solomon-lilim"
  dataSource = $payload.dataSource
  tier = $payload.tier
  timeLimitMs = $payload.timeLimitMs
  targetCount = $payload.targetCount
  totalCells = $payload.totalCells
  completedCells = $payload.completedCells
  solvers = $payload.solvers
  irxFeasible = "$irxFeasible/$($irxRows.Count)"
  ortoolsFeasible = "$ortFeasible/$($ortRows.Count)"
  pyvrpFeasible = "$pyvrpFeasible/$($pyvrpRows.Count)"
  pyvrpEvidenceGap = $pyvrpEvidenceGap
  hardViolationRows = $hardViolationRows.Count
  irxVsOrtools = @{ wins = $wins; ties = $ties; losses = $losses }
  compareRows = $compareRows
  officialSmokePass = ($payload.completedCells -eq $payload.totalCells -and $irxFeasible -eq $irxRows.Count -and $ortFeasible -eq $ortRows.Count -and $hardViolationRows.Count -eq 0)
  fullThreeSolverOfficialPass = ($pyvrpEvidenceGap -eq 0 -and $pyvrpFeasible -eq $pyvrpRows.Count)
  blockedClaims = @(
    "PyVRP official Solomon/LiLim baseline pass",
    "IRX official no-loss vs PyVRP",
    "IRX official no-loss vs BKS"
  )
}

$summaryPath = Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 80 | Set-Content $summaryPath
Write-Output "SUMMARY=$summaryPath"
if (-not $summary.officialSmokePass) { exit 1 }
