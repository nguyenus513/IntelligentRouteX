param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$DatasetTimeoutSeconds = 520,
  [string]$OutputDir = "artifacts/test-reports/final-certification/pdptw"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$datasets = @(
  "random-spread",
  "clustered-pickups-random-dropoffs",
  "random-pickups-clustered-dropoffs",
  "opposite-direction-dropoffs",
  "tight-capacity",
  "tight-deadline-case",
  "active-route-insertion"
)

& "$PSScriptRoot/run-clean-cache-gate.ps1" `
  -BaseUrl $BaseUrl `
  -Datasets $datasets `
  -Mode "QUALITY_BENCHMARK" `
  -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
  -OutputDir $OutputDir

function Test-PickupBeforeDropoff($run) {
  $violations = 0
  foreach ($route in @($run.routes)) {
    $picked = @{}
    foreach ($stop in @($route.stops)) {
      if ([string]::IsNullOrWhiteSpace($stop.orderId)) { continue }
      if ($stop.type -eq "PICKUP") { $picked[$stop.orderId] = $true }
      if ($stop.type -eq "DROPOFF" -and -not $picked.ContainsKey($stop.orderId)) { $violations++ }
    }
  }
  return $violations
}

function Test-Capacity($run) {
  $driverCapacity = @{}
  foreach ($driver in @($run.drivers)) { $driverCapacity[$driver.driverId] = [int]$driver.capacity }
  $violations = 0
  foreach ($route in @($run.routes)) {
    $capacity = if ($driverCapacity.ContainsKey($route.driverId)) { $driverCapacity[$route.driverId] } else { 999999 }
    $load = 0
    $maxLoad = 0
    foreach ($stop in @($route.stops)) {
      if ($stop.type -eq "PICKUP") { $load++ }
      if ($stop.type -eq "DROPOFF") { $load = [math]::Max(0, $load - 1) }
      $maxLoad = [math]::Max($maxLoad, $load)
    }
    if ($maxLoad -gt $capacity) { $violations++ }
  }
  return $violations
}

$summary = Get-Content (Join-Path $OutputDir "clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
$pickupViolations = 0
$capacityViolations = 0
foreach ($artifact in @($summary.artifacts)) {
  $run = Get-Content $artifact -Raw | ConvertFrom-Json
  $pickupViolations += Test-PickupBeforeDropoff $run
  $capacityViolations += Test-Capacity $run
}
$pass = [int]$summary.total -eq $datasets.Count -and [int]$summary.lateRegressionCount -eq 0 -and [int]$summary.dominanceFailures -eq 0 -and $pickupViolations -eq 0 -and $capacityViolations -eq 0
$gate = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $pass
  datasetCount = $summary.total
  pickupBeforeDropoffViolations = $pickupViolations
  capacityViolations = $capacityViolations
  lateRegression = $summary.lateRegressionCount
  dominanceFailures = $summary.dominanceFailures
  artifacts = @($summary.artifacts)
}
$path = Join-Path $OutputDir "pdptw-gate-summary.json"
$gate | ConvertTo-Json -Depth 50 | Set-Content $path
$gate
Write-Output "SUMMARY=$path"
if (-not $pass) { exit 1 }
