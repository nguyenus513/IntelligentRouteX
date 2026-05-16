param(
  [string]$BaseUrl = "http://localhost:8080",
  [string]$OutputDir = "artifacts/test-reports/rescue"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$dispatchBody = @{ orderCount = 20; driverCount = 4; scenarioType = "rescue-final-gate"; weatherProfile = "CLEAR"; trafficMode = "normal"; riskRate = 0.18 } | ConvertTo-Json
$before = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/dispatch/run" -ContentType "application/json" -Body $dispatchBody -TimeoutSec 240

$rescueBody = @{
  baseRunId = $before.runId
  events = @(
    @{ type = "driver-cancelled"; label = "Driver cancelled mid-route"; severity = "danger" },
    @{ type = "heavy-rain"; label = "Heavy traffic and rain zone"; severity = "warning" },
    @{ type = "restaurant-delay"; label = "Restaurant delay creates late risk"; severity = "warning" }
  )
} | ConvertTo-Json -Depth 20
$after = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/rescue/simulate" -ContentType "application/json" -Body $rescueBody -TimeoutSec 240

$artifact = Join-Path $OutputDir "rescue-gate-$($after.runId).json"
@{ before = $before; after = $after } | ConvertTo-Json -Depth 100 | Set-Content $artifact

$rescueRoutes = @($after.routes | Where-Object { $_.rescueStatus -eq "RESCUED" }).Count
$lateNotWorse = [int]$after.metrics.lateOrderCount -le [int]$before.metrics.lateOrderCount
$passed = $after.status -eq "COMPLETED" -and $after.comparison.beforeRunId -eq $before.runId -and $rescueRoutes -gt 0 -and $lateNotWorse -and $after.diagnostics.dispatchMode -eq "RESCUE"
$summary = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $passed
  beforeRunId = $before.runId
  afterRunId = $after.runId
  beforeLate = $before.metrics.lateOrderCount
  afterLate = $after.metrics.lateOrderCount
  rescuedRouteCount = $rescueRoutes
  artifact = $artifact
}
$summaryPath = Join-Path $OutputDir "rescue-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$summary
Write-Output "SUMMARY=$summaryPath"
if (-not $passed) { exit 1 }
