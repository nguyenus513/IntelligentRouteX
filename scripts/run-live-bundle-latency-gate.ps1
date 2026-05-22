param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-bundle-latency",
  [int]$MinBundleSize = 3
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 50) -TimeoutSec 90
}

function Stop-Key($Stop) { "$($Stop.type):$($Stop.orderId)" }

$failures = @()
try { $health = Invoke-Irx "/v1/health" } catch { throw "BACKEND_UNAVAILABLE_DURING_LATENCY_TEST: $($_.Exception.Message)" }
if ($health.routing.activeProvider -notmatch "osrm") { $failures += "ROUTING_PROVIDER_NOT_OSRM_$($health.routing.activeProvider)" }

$drivers = @(
  @{ driverId = "DRV_BUNDLE_A"; lat = 10.77220; lng = 106.66460; capacity = 100; currentLoad = 0; status = "IDLE" },
  @{ driverId = "DRV_BUNDLE_B"; lat = 10.82120; lng = 106.73140; capacity = 100; currentLoad = 0; status = "IDLE" }
)
$orders = @(
  @{ orderId = "ORD_BUNDLE_001"; pickupLat = 10.77550; pickupLng = 106.66820; dropoffLat = 10.78110; dropoffLng = 106.69050; demand = 4; deadlineMinutes = 100 },
  @{ orderId = "ORD_BUNDLE_002"; pickupLat = 10.77620; pickupLng = 106.66930; dropoffLat = 10.78220; dropoffLng = 106.69150; demand = 4; deadlineMinutes = 105 },
  @{ orderId = "ORD_BUNDLE_003"; pickupLat = 10.77700; pickupLng = 106.67000; dropoffLat = 10.78310; dropoffLng = 106.69280; demand = 4; deadlineMinutes = 110 },
  @{ orderId = "ORD_BUNDLE_004"; pickupLat = 10.77800; pickupLng = 106.67100; dropoffLat = 10.78420; dropoffLng = 106.69400; demand = 4; deadlineMinutes = 115 }
)

$session = Invoke-Irx "/v1/live/sessions" "POST" @{
  requestId = "bundle-latency-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  cityId = "hcm"
  profile = "LIVE_ROLLING"
  drivers = $drivers
  rollingConfig = @{ freezeNextStop = $true; freezePickedOrders = $true; adaptiveMlMode = "TOP_K_ASSISTED" }
}

$sendSw = [Diagnostics.Stopwatch]::StartNew()
$orderPostLatencies = @()
foreach ($order in $orders) {
  $one = [Diagnostics.Stopwatch]::StartNew()
  $response = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{
    requestId = "bundle-latency-order-$($order.orderId)"
    tenantId = "demo"
    order = $order
  }
  $one.Stop()
  $orderPostLatencies += [pscustomobject]@{ orderId = $order.orderId; clientPostMs = $one.ElapsedMilliseconds; backendAcceptedMs = $response.orderAcceptedLatencyMs }
}
$sendSw.Stop()

$cycleSw = [Diagnostics.Stopwatch]::StartNew()
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{
  requestId = "bundle-latency-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  trigger = "MANUAL"
  reason = "bundle-latency-gate"
  options = @{ maxRuntimeMs = 5000; returnDiagnostics = $true }
}
$cycleSw.Stop()
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"

$routes = @($state.activeRoutes)
$routeSummaries = @($routes | ForEach-Object {
  $route = $_
  $stops = @($route.stops)
  $orderIds = @($stops | Where-Object { $_.orderId } | ForEach-Object { $_.orderId } | Select-Object -Unique)
  foreach ($orderId in $orderIds) {
    $keys = @($stops | ForEach-Object { Stop-Key $_ })
    if (-not ($keys -contains "PICKUP:$orderId")) { $failures += "MISSING_PICKUP_$orderId" }
    if (-not ($keys -contains "DROPOFF:$orderId")) { $failures += "MISSING_DROPOFF_$orderId" }
    if ([array]::IndexOf($keys, "PICKUP:$orderId") -gt [array]::IndexOf($keys, "DROPOFF:$orderId")) { $failures += "PICKUP_AFTER_DROPOFF_$orderId" }
  }
  [pscustomobject]@{
    driverId = $route.driverId
    bundleSize = $orderIds.Count
    stopCount = $stops.Count
    polylinePointCount = @($route.polyline).Count
    sequence = (@($stops | ForEach-Object { Stop-Key $_ }) -join " -> ")
    assignedOrderIds = $orderIds
  }
})

$maxBundle = @($routeSummaries | Measure-Object bundleSize -Maximum).Maximum
if ($state.assignedOrders -lt $orders.Count) { $failures += "NOT_ALL_ORDERS_ASSIGNED_$($state.assignedOrders)_OF_$($orders.Count)" }
if ($maxBundle -lt $MinBundleSize) { $failures += "MAX_BUNDLE_UNDER_TARGET_$maxBundle" }
if (-not $cycle.latencyTrace -or [long]$cycle.latencyTrace.firstOrderToRouteReadyMs -le 0) { $failures += "MISSING_LATENCY_TRACE" }
$seedArchive = $cycle.decisionTrace.seedArchive
$ranking = @($seedArchive.ranking)
$winner = $seedArchive.winner
if (@($ranking).Count -lt 4) { $failures += "SEED_RANKING_UNDER_4_$(@($ranking).Count)" }
foreach ($seedName in @("VROOM", "ORTOOLS", "PYVRP", "IRX_NATIVE")) {
  if (-not @($ranking | Where-Object { $_.seed -eq $seedName })) { $failures += "MISSING_SEED_$seedName" }
}
if (-not $winner -or -not $winner.seed) { $failures += "MISSING_SEED_WINNER" }
$winnerRoutes = @($winner.routes)
if (@($winnerRoutes).Count -gt 0 -and @($routes).Count -gt 0) {
  $winnerSeq = (@($winnerRoutes[0].stopSequence) -join " -> ")
  $activeSeq = (@($routes[0].stops | Where-Object { $_.orderId } | ForEach-Object { Stop-Key $_ }) -join " -> ")
  if ($winnerSeq -ne $activeSeq) { $failures += "ACTIVE_ROUTE_NOT_FROM_WINNER_SEED" }
}

$summary = [pscustomobject]@{
  gate = "live-bundle-latency"
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  healthRouting = $health.routing
  orderPostLatencies = $orderPostLatencies
  sendAllOrdersClientMs = $sendSw.ElapsedMilliseconds
  cycleHttpMs = $cycleSw.ElapsedMilliseconds
  latencyTrace = $cycle.latencyTrace
  seedWinner = $winner
  seedRanking = $ranking
  assignedOrders = $state.assignedOrders
  bufferedOrders = $state.bufferedOrders
  maxBundleSize = $maxBundle
  routeSummaries = $routeSummaries
  failures = @($failures | Select-Object -Unique)
  overallPass = (@($failures | Select-Object -Unique).Count -eq 0)
}

$summaryPath = Join-Path $OutputDir "bundle-latency-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content $summaryPath -Encoding UTF8
Write-Output "SUMMARY=$summaryPath"
Write-Output "MAX_BUNDLE=$maxBundle"
Write-Output "FIRST_ORDER_TO_ROUTE_READY_MS=$($cycle.latencyTrace.firstOrderToRouteReadyMs)"
Write-Output "FAILURES=$($summary.failures -join ',')"
if (-not $summary.overallPass) { exit 1 }
