param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-runtime-root-cause",
  [int]$Polls = 8,
  [int]$DelayMs = 1000
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
  }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20)
}

function Driver-Snapshot($State) {
  @($State.driverStates) | ForEach-Object {
    [pscustomobject]@{
      driverId = $_.driverId
      lat = [double]$_.lat
      lng = [double]$_.lng
      status = $_.status
      routeId = $_.routeId
      nextStopType = $_.nextStopType
      nextOrderId = $_.nextOrderId
      speedKmh = $_.speedKmh
      movedMeters = $_.movedMeters
      totalMovedMeters = $_.totalMovedMeters
      movementTick = $_.movementTick
      stopIndex = $_.stopIndex
      polylineIndex = $_.polylineIndex
      polylineSize = $_.polylineSize
      remainingStops = $_.remainingStops
    }
  }
}

$startedAt = Get-Date
$health = Invoke-Irx "/v1/health"

$drivers = @(
  @{ driverId = "DRV_TEST_A"; lat = 10.77220; lng = 106.66460; capacity = 100; currentLoad = 0; status = "IDLE" },
  @{ driverId = "DRV_TEST_B"; lat = 10.80120; lng = 106.71140; capacity = 100; currentLoad = 0; status = "IDLE" }
)

$orders = @(
  @{ orderId = "ORD_RT_001"; pickupLat = 10.77550; pickupLng = 106.66820; dropoffLat = 10.78110; dropoffLng = 106.69050; demand = 4; deadlineMinutes = 80 },
  @{ orderId = "ORD_RT_002"; pickupLat = 10.77920; pickupLng = 106.67680; dropoffLat = 10.79280; dropoffLng = 106.70420; demand = 6; deadlineMinutes = 90 },
  @{ orderId = "ORD_RT_003"; pickupLat = 10.80420; pickupLng = 106.71580; dropoffLat = 10.78880; dropoffLng = 106.70120; demand = 5; deadlineMinutes = 75 }
)

$session = Invoke-Irx "/v1/live/sessions" "POST" @{
  requestId = "root-live-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  cityId = "hcm"
  profile = "LIVE_ROLLING"
  drivers = $drivers
  rollingConfig = @{ freezeNextStop = $true; freezePickedOrders = $true; adaptiveMlMode = "TOP_K_ASSISTED" }
}

foreach ($order in $orders) {
  Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{
    requestId = "root-order-$($order.orderId)"
    tenantId = "demo"
    order = $order
  } | Out-Null
}

$beforeCycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{
  requestId = "root-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  trigger = "MANUAL"
  reason = "live-runtime-root-cause"
  options = @{ maxRuntimeMs = 5000; returnDiagnostics = $true }
}

$ticks = @()
for ($i = 0; $i -lt $Polls; $i++) {
  Start-Sleep -Milliseconds $DelayMs
  $state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
  $ticks += [pscustomobject]@{
    index = $i
    at = (Get-Date).ToString("o")
    bufferedOrders = $state.bufferedOrders
    assignedOrders = $state.assignedOrders
    activeRoutes = @($state.activeRoutes).Count
    routeStopSequences = @($state.activeRoutes | ForEach-Object { @($_.stops | ForEach-Object { "$($_.type):$($_.orderId)" }) -join " -> " })
    routePolylineSizes = @($state.activeRoutes | ForEach-Object { @($_.polyline).Count })
    removedPickups = @($state.removedMarkers.pickups)
    removedDropoffs = @($state.removedMarkers.dropoffs)
    drivers = @(Driver-Snapshot $state)
    rawState = $state
  }
}

$firstDrivers = @($ticks[0].drivers)
$lastDrivers = @($ticks[-1].drivers)
$driverDeltas = @()
foreach ($last in $lastDrivers) {
  $first = $firstDrivers | Where-Object { $_.driverId -eq $last.driverId } | Select-Object -First 1
  if ($first) {
    $driverDeltas += [pscustomobject]@{
      driverId = $last.driverId
      firstLat = $first.lat
      firstLng = $first.lng
      lastLat = $last.lat
      lastLng = $last.lng
      tickDelta = ([int]$last.movementTick) - ([int]$first.movementTick)
      totalMovedMeters = [double]$last.totalMovedMeters
      moved = (($first.lat -ne $last.lat) -or ($first.lng -ne $last.lng) -or ([double]$last.totalMovedMeters -gt [double]$first.totalMovedMeters))
      firstStatus = $first.status
      lastStatus = $last.status
      routeId = $last.routeId
    }
  }
}

$routes = @($ticks[-1].rawState.activeRoutes)
$routeChecks = @($routes | ForEach-Object {
  $stops = @($_.stops)
  $pickupIndex = @{}
  $dropoffViolations = @()
  for ($i = 0; $i -lt $stops.Count; $i++) {
    $stop = $stops[$i]
    if ($stop.type -eq "PICKUP") { $pickupIndex[$stop.orderId] = $i }
    if ($stop.type -eq "DROPOFF" -and (-not $pickupIndex.ContainsKey($stop.orderId))) { $dropoffViolations += $stop.orderId }
  }
  [pscustomobject]@{
    routeId = $_.routeId
    driverId = $_.driverId
    startsFromDriver = ($stops.Count -gt 0 -and $stops[0].type -eq "DRIVER_START")
    stopCount = $stops.Count
    polylineSize = @($_.polyline).Count
    dropoffBeforePickup = $dropoffViolations
    sequence = @($stops | ForEach-Object { "$($_.type):$($_.orderId)" }) -join " -> "
  }
})

$anyDriverMoved = @($driverDeltas | Where-Object { $_.moved }).Count -gt 0
$allRoutesStartFromDriver = @($routeChecks | Where-Object { -not $_.startsFromDriver }).Count -eq 0 -and @($routeChecks).Count -gt 0
$allRoutesHavePolyline = @($routeChecks | Where-Object { $_.polylineSize -le 1 }).Count -eq 0 -and @($routeChecks).Count -gt 0
$noPrecedenceViolation = @($routeChecks | Where-Object { @($_.dropoffBeforePickup).Count -gt 0 }).Count -eq 0

$rootCause = "UNKNOWN"
if (@($routes).Count -eq 0) { $rootCause = "NO_ACTIVE_ROUTES_AFTER_CYCLE" }
elseif (-not $allRoutesStartFromDriver) { $rootCause = "ROUTE_DOES_NOT_START_FROM_DRIVER" }
elseif (-not $allRoutesHavePolyline) { $rootCause = "BACKEND_ROUTE_GEOMETRY_MISSING" }
elseif (-not $anyDriverMoved) { $rootCause = "BACKEND_DRIVER_RUNTIME_NOT_MOVING" }
elseif (-not $noPrecedenceViolation) { $rootCause = "PICKUP_DROPOFF_PRECEDENCE_VIOLATION" }
else { $rootCause = "BACKEND_RUNTIME_OK_CHECK_FE_RENDERING_IF_UI_STILL_STATIC" }

$summary = [pscustomobject]@{
  gate = "live-runtime-root-cause"
  startedAt = $startedAt.ToString("o")
  finishedAt = (Get-Date).ToString("o")
  baseUrl = $BaseUrl
  health = $health
  sessionId = $session.sessionId
  cycle = $cycle
  beforeCycle = $beforeCycle
  routeChecks = $routeChecks
  driverDeltas = $driverDeltas
  anyDriverMoved = $anyDriverMoved
  allRoutesStartFromDriver = $allRoutesStartFromDriver
  allRoutesHavePolyline = $allRoutesHavePolyline
  noPrecedenceViolation = $noPrecedenceViolation
  removedPickupsFirstTick = $ticks[0].removedPickups
  removedDropoffsFirstTick = $ticks[0].removedDropoffs
  removedPickupsLastTick = $ticks[-1].removedPickups
  removedDropoffsLastTick = $ticks[-1].removedDropoffs
  rootCause = $rootCause
  overallPass = ($rootCause -eq "BACKEND_RUNTIME_OK_CHECK_FE_RENDERING_IF_UI_STILL_STATIC")
}

$ticksPath = Join-Path $OutputDir "state-ticks.json"
$summaryPath = Join-Path $OutputDir "root-cause-summary.json"
$ticks | ConvertTo-Json -Depth 80 | Set-Content $ticksPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 80 | Set-Content $summaryPath -Encoding UTF8
Write-Output "TICKS=$ticksPath"
Write-Output "SUMMARY=$summaryPath"
Write-Output "ROOT_CAUSE=$rootCause"
if (-not $summary.overallPass) { exit 1 }
