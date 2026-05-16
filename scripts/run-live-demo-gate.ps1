param(
  [string]$BaseUrl = "http://localhost:8080",
  [string]$OutputDir = "artifacts/test-reports/live"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$policy = @{ cycleIntervalSeconds = 10; maxOrderWaitSeconds = 60; maxDeferCount = 2; mustDispatchAfterSeconds = 0 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/start" -ContentType "application/json" -Body $policy -TimeoutSec 30 | Out-Null

$drivers = @()
for ($i = 1; $i -le 4; $i++) {
  $drivers += @{ driverId = "DRV-LIVE-$i"; lat = 10.76 + ($i * 0.006); lng = 106.68 + ($i * 0.006); timestamp = (Get-Date).ToString("o"); heading = 0; speed = 20; activeRouteId = ""; status = "AVAILABLE" }
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/drivers/location" -ContentType "application/json" -Body (@{ drivers = $drivers } | ConvertTo-Json -Depth 20) -TimeoutSec 30 | Out-Null

$orders = @()
for ($i = 1; $i -le 20; $i++) {
  $orders += @{ orderId = "ORD-LIVE-$i"; pickupLat = 10.75 + ($i * 0.001); pickupLng = 106.67 + ($i * 0.001); dropoffLat = 10.79 + ($i * 0.001); dropoffLng = 106.71 + ($i * 0.001); deadlineMinutes = 45; priority = 1 }
}
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/orders" -ContentType "application/json" -Body (@{ orders = $orders } | ConvertTo-Json -Depth 20) -TimeoutSec 30 | Out-Null

$cycle = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/live/cycles/run-now" -TimeoutSec 180
$artifact = Join-Path $OutputDir "live-demo-gate-$($cycle.cycleId).json"
$cycle | ConvertTo-Json -Depth 100 | Set-Content $artifact

$passed = $cycle.inputOrderCount -eq 20 -and $cycle.driverCount -eq 4 -and $cycle.assignedOrderIds.Count -gt 0 -and $cycle.diagnostics.coreEntrypoint -eq "UnifiedDispatchCore.dispatch" -and $cycle.diagnostics.dispatchMode -eq "LIVE_ROLLING"
$summary = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $passed
  cycleId = $cycle.cycleId
  inputOrderCount = $cycle.inputOrderCount
  assignedOrderCount = $cycle.assignedOrderIds.Count
  deferredOrderCount = $cycle.deferredOrderIds.Count
  expiredOrderCount = $cycle.expiredOrderIds.Count
  unifiedCoreMode = $cycle.diagnostics.dispatchMode
  artifact = $artifact
}
$summaryPath = Join-Path $OutputDir "live-demo-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$summary
Write-Output "SUMMARY=$summaryPath"
if (-not $passed) { exit 1 }
