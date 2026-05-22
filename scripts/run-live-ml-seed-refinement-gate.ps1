param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-ml-seed-refinement"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }
function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 50) -TimeoutSec 120
}
$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_ML_GATE_A"; lat = 10.7722; lng = 106.6646; capacity = 100 },
  @{ driverId = "DRV_ML_GATE_B"; lat = 10.8212; lng = 106.7314; capacity = 100 }
)
$orders = @(
  @{ orderId = "ORD_ML_GATE_001"; pickupLat = 10.7755; pickupLng = 106.6682; dropoffLat = 10.7811; dropoffLng = 106.6905; demand = 1; deadlineMinutes = 80 },
  @{ orderId = "ORD_ML_GATE_002"; pickupLat = 10.7762; pickupLng = 106.6693; dropoffLat = 10.7822; dropoffLng = 106.6915; demand = 1; deadlineMinutes = 85 },
  @{ orderId = "ORD_ML_GATE_003"; pickupLat = 10.7770; pickupLng = 106.6700; dropoffLat = 10.7831; dropoffLng = 106.6928; demand = 1; deadlineMinutes = 90 },
  @{ orderId = "ORD_ML_GATE_004"; pickupLat = 10.7780; pickupLng = 106.6710; dropoffLat = 10.7842; dropoffLng = 106.6940; demand = 1; deadlineMinutes = 95 }
)
$session = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId = "live-ml-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers }
foreach ($order in $orders) {
  Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{ requestId = "live-ml-order-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null
}
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{ requestId = "live-ml-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "ML_HYBRID_PD_LNS" }
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$refinement = @($cycle.decisionTrace.hybridRefinement.routes)[0]
$failures = @()
if ($cycle.decisionTrace.finalSelection.selectedSource -ne "IRX_HYBRID_REFINEMENT") { $failures += "final source is not IRX_HYBRID_REFINEMENT" }
if (-not $cycle.decisionTrace.finalSelection.seedSource) { $failures += "missing seedSource" }
if (-not $refinement.mlExecuted) { $failures += "ML did not execute" }
if ([int]$refinement.evaluatedInsertions -le 0) { $failures += "evaluatedInsertions is zero" }
if ([int]$refinement.feasibleInsertions -le 0) { $failures += "feasibleInsertions is zero" }
if ($refinement.dominanceGuard -notin @("PASS", "ROLLBACK")) { $failures += "missing dominance guard verdict" }
if (@($state.activeRoutes).Count -lt 1) { $failures += "no active route" }
$firstRoute = @($state.activeRoutes)[0]
$pickupCount = @($firstRoute.stops | Where-Object { $_.type -eq "PICKUP" }).Count
$dropoffCount = @($firstRoute.stops | Where-Object { $_.type -eq "DROPOFF" }).Count
if ($pickupCount -lt 4 -or $dropoffCount -lt 4) { $failures += "route does not contain 4 pickup/dropoff pairs" }
$summary = [ordered]@{
  gate = "live-ml-seed-refinement"
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  healthRouting = $health.routing
  seedSource = $cycle.decisionTrace.finalSelection.seedSource
  selectedSource = $cycle.decisionTrace.finalSelection.selectedSource
  finalOptimizer = $cycle.decisionTrace.finalSelection.finalOptimizer
  mlStatus = $refinement.status
  optimizer = $refinement.optimizer
  mlExecuted = $refinement.mlExecuted
  mode = $refinement.mode
  evaluatedOrders = $refinement.evaluatedOrders
  evaluatedInsertions = $refinement.evaluatedInsertions
  feasibleInsertions = $refinement.feasibleInsertions
  acceptedMutations = $refinement.acceptedMutations
  dominanceGuard = $refinement.dominanceGuard
  rollbackReason = $refinement.rollbackReason
  mlParticipation = $refinement.mlParticipation
  activeRouteId = $firstRoute.routeId
  pickupCount = $pickupCount
  dropoffCount = $dropoffCount
  failures = $failures
  overallPass = $failures.Count -eq 0
}
$summaryPath = Join-Path $OutputDir "live-ml-seed-refinement-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 $summaryPath
$cycle | ConvertTo-Json -Depth 60 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "cycle-response.json")
$state | ConvertTo-Json -Depth 60 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "state-response.json")
Write-Host "SUMMARY=$summaryPath"
Write-Host "ML_EXECUTED=$($summary.mlExecuted)"
Write-Host "EVALUATED_INSERTIONS=$($summary.evaluatedInsertions)"
Write-Host "DOMINANCE_GUARD=$($summary.dominanceGuard)"
Write-Host "FAILURES=$($failures -join ';')"
if ($failures.Count -gt 0) { exit 1 }
