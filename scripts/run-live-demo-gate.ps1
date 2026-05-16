param(
  [string]$BaseUrl = "http://localhost:8080",
  [string]$OutputDir = "artifacts/test-reports/live"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$body = @{ orderCount = 20; driverCount = 4; scenarioType = "live-rolling-smoke"; weatherProfile = "CLEAR"; trafficMode = "normal"; riskRate = 0.14 } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/dispatch/run" -ContentType "application/json" -Body $body -TimeoutSec 180
$artifact = Join-Path $OutputDir "live-demo-gate-$($run.runId).json"
$run | ConvertTo-Json -Depth 100 | Set-Content $artifact

$passed = $run.status -eq "COMPLETED" -and $run.metrics.assignedOrderCount -gt 0 -and $run.diagnostics.coverageSummary -ne $null
$summary = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $passed
  runId = $run.runId
  assignedOrderCount = $run.metrics.assignedOrderCount
  lateOrderCount = $run.metrics.lateOrderCount
  unifiedCoreMode = $run.diagnostics.dispatchMode
  artifact = $artifact
}
$summaryPath = Join-Path $OutputDir "live-demo-gate-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
$summary
Write-Output "SUMMARY=$summaryPath"
if (-not $passed) { exit 1 }
