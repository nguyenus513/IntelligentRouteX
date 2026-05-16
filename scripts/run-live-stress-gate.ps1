param(
  [string]$BaseUrl = "http://localhost:8080",
  [string]$OutputDir = "artifacts/test-reports/live-stress"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$policy = @{ cycleIntervalSeconds = 10; maxOrderWaitSeconds = 60; maxDeferCount = 2; mustDispatchAfterSeconds = 0 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/start" -ContentType "application/json" -Body $policy -TimeoutSec 30 | Out-Null

function Push-Drivers([int]$Cycle, [double]$Shift = 0.0) {
  $drivers = @()
  for ($i = 1; $i -le 4; $i++) {
    $far = if ($Cycle -ge 3 -and $i -eq 4) { 0.08 } else { 0.0 }
    $drivers += @{ driverId = "DRV-STRESS-$i"; lat = 10.76 + ($i * 0.006) + $Shift + $far; lng = 106.68 + ($i * 0.006) + $Shift + $far; timestamp = (Get-Date).ToString("o"); heading = 0; speed = 18; activeRouteId = ""; status = "AVAILABLE" }
  }
  Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/drivers/location" -ContentType "application/json" -Body (@{ drivers = $drivers } | ConvertTo-Json -Depth 20) -TimeoutSec 30 | Out-Null
}

function Push-Orders([string]$Prefix, [int]$Count, [int]$Offset, [int]$Deadline = 45, [int]$Priority = 1) {
  $orders = @()
  for ($i = 1; $i -le $Count; $i++) {
    $n = $Offset + $i
    $orders += @{ orderId = "$Prefix-$n"; pickupLat = 10.75 + ($n * 0.0008); pickupLng = 106.67 + ($n * 0.0008); dropoffLat = 10.79 + ($n * 0.0009); dropoffLng = 106.71 + ($n * 0.0009); deadlineMinutes = $Deadline; priority = $Priority }
  }
  Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/orders" -ContentType "application/json" -Body (@{ orders = $orders } | ConvertTo-Json -Depth 20) -TimeoutSec 30 | Out-Null
}

$cycles = @()
Push-Drivers 1
Push-Orders "ORD-STRESS-A" 20 0 45 1
$cycles += Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/cycles/run-now" -TimeoutSec 240

Push-Drivers 2 0.003
Push-Orders "ORD-STRESS-B" 10 20 45 1
$cycles += Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/cycles/run-now" -TimeoutSec 240

Push-Drivers 3 0.006
Push-Orders "ORD-STRESS-C" 5 30 22 3
$cycles += Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/cycles/run-now" -TimeoutSec 240

Push-Drivers 4 0.009
$cycles += Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/cycles/run-now" -TimeoutSec 240

$state = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/live/state" -TimeoutSec 60
$artifact = Join-Path $OutputDir "live-stress-gate.json"
@{ cycles = $cycles; state = $state } | ConvertTo-Json -Depth 100 | Set-Content $artifact

$bufferedOld = @($state.orders | Where-Object { $_.status -eq "BUFFERED" }).Count
$assigned = ($cycles | ForEach-Object { $_.assignedOrderIds.Count } | Measure-Object -Sum).Sum
$passed = $cycles.Count -ge 4 -and $assigned -gt 0 -and $bufferedOld -eq 0 -and (@($cycles | Where-Object { $_.diagnostics.coreEntrypoint -ne "UnifiedDispatchCore.dispatch" -or $_.diagnostics.dispatchMode -ne "LIVE_ROLLING" }).Count -eq 0)
$summary = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $passed
  cycleCount = $cycles.Count
  assignedOrderCount = $assigned
  bufferedOrderCount = $bufferedOld
  mode = "LIVE_ROLLING"
  artifact = $artifact
}
$summaryPath = Join-Path $OutputDir "live-stress-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$summary
Write-Output "SUMMARY=$summaryPath"
if (-not $passed) { exit 1 }
