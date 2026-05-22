param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-osrm-only-routing"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }
function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 100) -TimeoutSec 240
}
function Text-Contains($Object, [string]$Needle) {
  $text = $Object | ConvertTo-Json -Depth 100 -Compress
  return $text.Contains($Needle)
}
$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_OSRM_ONLY_A"; lat = 10.7700; lng = 106.6600; capacity = 100 },
  @{ driverId = "DRV_OSRM_ONLY_B"; lat = 10.8300; lng = 106.7300; capacity = 100 }
)
$orders = @(
  @{ orderId = "ORD_OSRM_ONLY_001"; pickupLat = 10.7710; pickupLng = 106.6610; dropoffLat = 10.7730; dropoffLng = 106.6630; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_ONLY_002"; pickupLat = 10.7720; pickupLng = 106.6620; dropoffLat = 10.7750; dropoffLng = 106.6650; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_ONLY_003"; pickupLat = 10.7740; pickupLng = 106.6640; dropoffLat = 10.7770; dropoffLng = 106.6670; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_ONLY_004"; pickupLat = 10.7760; pickupLng = 106.6660; dropoffLat = 10.7780; dropoffLng = 106.6680; demand = 1; deadlineMinutes = 120 }
)
$session = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId = "osrm-only-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers }
foreach($order in $orders){ Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{ requestId = "osrm-only-order-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null }
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{ requestId = "osrm-only-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "MAX_IRX" }
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$routes = @($state.activeRoutes)
$ref = @($cycle.decisionTrace.hybridRefinement.routes)[0]
$failures = @()
if ($health.routing.configuredProvider -ne 'osrm') { $failures += "routing provider is not osrm" }
if ($health.routing.activeProvider -notlike '*osrm*') { $failures += "active routing provider is not osrm" }
if ($cycle.status -ne 'COMPLETED') { $failures += "cycle did not complete" }
if ($routes.Count -lt 1) { $failures += "no active routes returned" }
foreach($route in $routes) {
  if ($route.geometryMode -ne 'ROAD_ROUTE') { $failures += "route $($route.routeId) geometryMode is $($route.geometryMode)" }
  if (@($route.polyline).Count -le 2) { $failures += "route $($route.routeId) missing backend OSRM polyline" }
  if (($route.totalDistanceKm -as [double]) -le 0) { $failures += "route $($route.routeId) distance is not positive" }
  if (($route.totalEtaMinutes -as [double]) -le 0) { $failures += "route $($route.routeId) eta is not positive" }
}
if ($ref.routingPolicy -ne 'OSRM_ONLY') { $failures += "hybrid refinement routingPolicy is not OSRM_ONLY" }
if ($ref.roadDistanceSource -ne 'OSRM_ROUTE_LEGS') { $failures += "hybrid refinement distance source is not OSRM_ROUTE_LEGS" }
if (-not $ref.osrmRequired) { $failures += "hybrid refinement osrmRequired is not true" }
if (Text-Contains $cycle 'STRAIGHT_LINE') { $failures += "cycle payload contains STRAIGHT_LINE" }
if (Text-Contains $state 'STRAIGHT_LINE') { $failures += "state payload contains STRAIGHT_LINE" }
if (Text-Contains $cycle 'synthetic-local-matrix') { $failures += "cycle payload contains synthetic-local-matrix" }
if (Text-Contains $cycle 'routing-primary-shortlist-only') { $failures += "cycle payload contains routing-primary-shortlist-only" }
if (Text-Contains $cycle 'routing-primary-budget-exhausted') { $failures += "cycle payload contains routing-primary-budget-exhausted" }
$summary = [ordered]@{
  gate = "live-osrm-only-routing"
  sessionId = $session.sessionId
  healthRouting = $health.routing
  routingPolicy = $ref.routingPolicy
  roadDistanceSource = $ref.roadDistanceSource
  routeCount = $routes.Count
  geometryModes = @($routes | ForEach-Object { $_.geometryMode })
  polylinePointCounts = @($routes | ForEach-Object { @($_.polyline).Count })
  distancesKm = @($routes | ForEach-Object { $_.totalDistanceKm })
  etaMinutes = @($routes | ForEach-Object { $_.totalEtaMinutes })
  failures = $failures
  overallPass = $failures.Count -eq 0
}
$summaryPath = Join-Path $OutputDir "live-osrm-only-routing-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 $summaryPath
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "cycle-response.json")
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "state-response.json")
Write-Host "SUMMARY=$summaryPath"
Write-Host "ROUTING_POLICY=$($summary.routingPolicy)"
Write-Host "GEOMETRY_MODES=$($summary.geometryModes -join ',')"
Write-Host "POLYLINE_POINTS=$($summary.polylinePointCounts -join ',')"
Write-Host "FAILURES=$($failures -join ';')"
if($failures.Count -gt 0){ exit 1 }

