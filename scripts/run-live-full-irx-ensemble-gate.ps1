param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-full-irx-ensemble",
  [string]$Mode = "MAX_IRX"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }
function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 70) -TimeoutSec 180
}
$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_FULL_A"; lat = 10.7722; lng = 106.6646; capacity = 100 },
  @{ driverId = "DRV_FULL_B"; lat = 10.8212; lng = 106.7314; capacity = 100 },
  @{ driverId = "DRV_FULL_C"; lat = 10.7590; lng = 106.7009; capacity = 100 }
)
$orders = @(
  @{ orderId = "ORD_FULL_001"; pickupLat = 10.7755; pickupLng = 106.6682; dropoffLat = 10.7811; dropoffLng = 106.6905; demand = 1; deadlineMinutes = 80 },
  @{ orderId = "ORD_FULL_002"; pickupLat = 10.7762; pickupLng = 106.6693; dropoffLat = 10.7822; dropoffLng = 106.6915; demand = 1; deadlineMinutes = 85 },
  @{ orderId = "ORD_FULL_003"; pickupLat = 10.7770; pickupLng = 106.6700; dropoffLat = 10.7831; dropoffLng = 106.6928; demand = 1; deadlineMinutes = 90 },
  @{ orderId = "ORD_FULL_004"; pickupLat = 10.7780; pickupLng = 106.6710; dropoffLat = 10.7842; dropoffLng = 106.6940; demand = 1; deadlineMinutes = 95 }
)
$session = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId = "full-irx-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers }
foreach ($order in $orders) {
  Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{ requestId = "full-irx-order-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null
}
$sw = [Diagnostics.Stopwatch]::StartNew()
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{ requestId = "full-irx-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = $Mode }
$sw.Stop()
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$refinement = @($cycle.decisionTrace.hybridRefinement.routes)[0]
$candidates = @($refinement.candidates)
$winner = $refinement.winner
$firstRoute = @($state.activeRoutes)[0]
$pickupCount = @($firstRoute.stops | Where-Object { $_.type -eq "PICKUP" }).Count
$dropoffCount = @($firstRoute.stops | Where-Object { $_.type -eq "DROPOFF" }).Count
$failures = @()
if ($cycle.decisionTrace.finalSelection.selectedSource -ne "IRX_FULL_ENSEMBLE") { $failures += "final source is not IRX_FULL_ENSEMBLE" }
if (-not $cycle.decisionTrace.finalSelection.seedSource) { $failures += "missing seedSource" }
if (-not $cycle.decisionTrace.finalSelection.selectedOptimizer) { $failures += "missing selectedOptimizer" }
if ($candidates.Count -lt 3) { $failures += "less than 3 optimizer candidates" }
if (($candidates | Measure-Object -Property evaluatedInsertions -Sum).Sum -le 0) { $failures += "evaluatedInsertions is zero" }
if ($refinement.dominanceGuard -notin @("PASS", "ROLLBACK")) { $failures += "missing dominance guard verdict" }
if ($pickupCount -lt 4 -or $dropoffCount -lt 4) { $failures += "route does not contain 4 pickup/dropoff pairs" }
if ($sw.ElapsedMilliseconds -gt 20000) { $failures += "cycle HTTP timeout budget exceeded" }
$summary = [ordered]@{
  gate = "live-full-irx-ensemble"
  mode = $Mode
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  healthRouting = $health.routing
  cycleHttpMs = $sw.ElapsedMilliseconds
  seedSource = $cycle.decisionTrace.finalSelection.seedSource
  selectedSource = $cycle.decisionTrace.finalSelection.selectedSource
  finalOptimizer = $cycle.decisionTrace.finalSelection.finalOptimizer
  selectedOptimizer = $cycle.decisionTrace.finalSelection.selectedOptimizer
  candidateCount = $candidates.Count
  candidateOptimizers = @($candidates | ForEach-Object { $_.optimizer })
  winner = $winner
  evaluatedInsertions = ($candidates | Measure-Object -Property evaluatedInsertions -Sum).Sum
  feasibleInsertions = ($candidates | Measure-Object -Property feasibleInsertions -Sum).Sum
  acceptedMutations = ($candidates | Measure-Object -Property acceptedMutations -Sum).Sum
  dominanceGuard = $refinement.dominanceGuard
  activeRouteId = $firstRoute.routeId
  pickupCount = $pickupCount
  dropoffCount = $dropoffCount
  failures = $failures
  overallPass = $failures.Count -eq 0
}
$summaryPath = Join-Path $OutputDir "live-full-irx-ensemble-summary.json"
$summary | ConvertTo-Json -Depth 70 | Set-Content -Encoding UTF8 $summaryPath
$cycle | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "cycle-response.json")
$state | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "state-response.json")
Write-Host "SUMMARY=$summaryPath"
Write-Host "SELECTED_OPTIMIZER=$($summary.selectedOptimizer)"
Write-Host "CANDIDATE_COUNT=$($summary.candidateCount)"
Write-Host "EVALUATED_INSERTIONS=$($summary.evaluatedInsertions)"
Write-Host "DOMINANCE_GUARD=$($summary.dominanceGuard)"
Write-Host "FAILURES=$($failures -join ';')"
if ($failures.Count -gt 0) { exit 1 }
