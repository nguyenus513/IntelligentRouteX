param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-route-geometry-sequence",
  [int]$MinDensePoints = 18
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 40) -TimeoutSec 60
}

function Stop-Key($Stop) { "$($Stop.type):$($Stop.orderId)" }

$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_GEOM_A"; lat = 10.77220; lng = 106.66460; capacity = 100; currentLoad = 0; status = "IDLE" },
  @{ driverId = "DRV_GEOM_B"; lat = 10.80120; lng = 106.71140; capacity = 100; currentLoad = 0; status = "IDLE" }
)
$orders = @(
  @{ orderId = "ORD_GEOM_001"; pickupLat = 10.77550; pickupLng = 106.66820; dropoffLat = 10.78110; dropoffLng = 106.69050; demand = 4; deadlineMinutes = 80 },
  @{ orderId = "ORD_GEOM_002"; pickupLat = 10.77920; pickupLng = 106.67680; dropoffLat = 10.79280; dropoffLng = 106.70420; demand = 6; deadlineMinutes = 90 },
  @{ orderId = "ORD_GEOM_003"; pickupLat = 10.80420; pickupLng = 106.71580; dropoffLat = 10.78880; dropoffLng = 106.70120; demand = 5; deadlineMinutes = 75 }
)

$session = Invoke-Irx "/v1/live/sessions" "POST" @{
  requestId = "geometry-sequence-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  cityId = "hcm"
  profile = "LIVE_ROLLING"
  drivers = $drivers
  rollingConfig = @{ freezeNextStop = $true; freezePickedOrders = $true; adaptiveMlMode = "TOP_K_ASSISTED" }
}

foreach ($order in $orders) {
  Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{
    requestId = "geometry-sequence-order-$($order.orderId)"
    tenantId = "demo"
    order = $order
  } | Out-Null
}

$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{
  requestId = "geometry-sequence-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  trigger = "MANUAL"
  reason = "geometry-sequence-gate"
  options = @{ maxRuntimeMs = 5000; returnDiagnostics = $true }
}
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"

$routes = @($state.activeRoutes)
$failures = @()
if (@($routes).Count -eq 0) { $failures += "NO_ACTIVE_ROUTES" }

$routeSummaries = @($routes | ForEach-Object {
  $route = $_
  $stops = @($route.stops)
  $polyline = @($route.polyline)
  $orderIds = @($stops | Where-Object { $_.orderId } | ForEach-Object { $_.orderId } | Select-Object -Unique)
  foreach ($orderId in $orderIds) {
    $keys = @($stops | Where-Object { $_.orderId -eq $orderId } | ForEach-Object { Stop-Key $_ })
    if (-not ($keys -contains "PICKUP:$orderId")) { $failures += "MISSING_PICKUP_$orderId" }
    if (-not ($keys -contains "DROPOFF:$orderId")) { $failures += "MISSING_DROPOFF_$orderId" }
    $pickupIndex = [array]::IndexOf(@($stops | ForEach-Object { Stop-Key $_ }), "PICKUP:$orderId")
    $dropoffIndex = [array]::IndexOf(@($stops | ForEach-Object { Stop-Key $_ }), "DROPOFF:$orderId")
    if ($pickupIndex -ge 0 -and $dropoffIndex -ge 0 -and $pickupIndex -gt $dropoffIndex) { $failures += "PICKUP_AFTER_DROPOFF_$orderId" }
  }
  $denseThreshold = [Math]::Max($MinDensePoints, $stops.Count * 3)
  if ($polyline.Count -lt $denseThreshold) { $failures += "ROUTE_GEOMETRY_TOO_SPARSE_$($route.driverId)_$($polyline.Count)_LT_$denseThreshold" }
  [pscustomobject]@{
    routeId = $route.routeId
    driverId = $route.driverId
    stopCount = $stops.Count
    polylinePointCount = $polyline.Count
    denseThreshold = $denseThreshold
    sequence = (@($stops | ForEach-Object { Stop-Key $_ }) -join " -> ")
    assignedOrderIds = $orderIds
  }
})

$traceRoutes = @($state.decisionTrace.routeOrdering)
if (@($traceRoutes).Count -eq 0) { $failures += "MISSING_DECISION_TRACE_ROUTE_ORDERING" }

$summary = [pscustomobject]@{
  gate = "live-route-geometry-sequence"
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  health = $health
  cycleStatus = $cycle.status
  assignedOrders = $state.assignedOrders
  bufferedOrders = $state.bufferedOrders
  routeSummaries = $routeSummaries
  traceRouteOrdering = $traceRoutes
  failures = @($failures | Select-Object -Unique)
  overallPass = (@($failures | Select-Object -Unique).Count -eq 0)
}

$summaryPath = Join-Path $OutputDir "route-geometry-sequence-summary.json"
$summary | ConvertTo-Json -Depth 100 | Set-Content $summaryPath -Encoding UTF8
Write-Output "SUMMARY=$summaryPath"
Write-Output "FAILURES=$($summary.failures -join ',')"
if (-not $summary.overallPass) { exit 1 }
