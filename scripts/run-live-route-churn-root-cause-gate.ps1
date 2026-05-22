param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-route-churn-root-cause",
  [int]$DelayMs = 1000
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30)
}

function Route-Signatures($State) {
  @($State.activeRoutes) | ForEach-Object {
    $sequence = @($_.stops | ForEach-Object { "$($_.type):$($_.orderId)#$($_.sequence)" }) -join " -> "
    $orders = @($_.stops | Where-Object { $_.orderId } | ForEach-Object { $_.orderId } | Select-Object -Unique)
    [pscustomobject]@{
      routeId = $_.routeId
      driverId = $_.driverId
      orders = $orders
      sequence = $sequence
      stopCount = @($_.stops).Count
      polylineSize = @($_.polyline).Count
      startsFromDriver = (@($_.stops).Count -gt 0 -and @($_.stops)[0].type -eq "DRIVER_START")
    }
  }
}

function Driver-Signatures($State) {
  @($State.driverStates) | ForEach-Object {
    [pscustomobject]@{
      driverId = $_.driverId
      lat = $_.lat
      lng = $_.lng
      routeId = $_.routeId
      status = $_.status
      nextStopType = $_.nextStopType
      nextOrderId = $_.nextOrderId
      movementTick = $_.movementTick
      movedMeters = $_.movedMeters
      totalMovedMeters = $_.totalMovedMeters
      stopIndex = $_.stopIndex
      polylineIndex = $_.polylineIndex
    }
  }
}

function Add-Order($SessionId, $Order) {
  Invoke-Irx "/v1/live/sessions/$SessionId/orders" "POST" @{
    requestId = "churn-order-$($Order.orderId)"
    tenantId = "demo"
    order = $Order
  } | Out-Null
}

function Run-Cycle($SessionId, $Reason) {
  Invoke-Irx "/v1/live/sessions/$SessionId/cycles" "POST" @{
    requestId = "churn-cycle-$Reason-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
    tenantId = "demo"
    trigger = "MANUAL"
    reason = $Reason
    options = @{ maxRuntimeMs = 5000; returnDiagnostics = $true }
  }
}

function Capture($Label, $SessionId, $Cycle = $null) {
  $state = Invoke-Irx "/v1/live/sessions/$SessionId/state"
  [pscustomobject]@{
    label = $Label
    at = (Get-Date).ToString("o")
    bufferedOrders = $state.bufferedOrders
    assignedOrders = $state.assignedOrders
    routeChurnPercent = if ($Cycle) { $Cycle.routeChurnPercent } else { $null }
    cycle = $Cycle
    routes = @(Route-Signatures $state)
    drivers = @(Driver-Signatures $state)
    removedMarkers = $state.removedMarkers
    bufferItems = $state.bufferItems
    rawState = $state
  }
}

function Order-Map($Routes) {
  $map = @{}
  foreach ($route in @($Routes)) {
    foreach ($order in @($route.orders)) { $map[$order] = $route.driverId }
  }
  return $map
}

function Compare-Routes($Before, $After) {
  $beforeMap = Order-Map $Before.routes
  $afterMap = Order-Map $After.routes
  $lost = @()
  $changedDriver = @()
  foreach ($order in $beforeMap.Keys) {
    if (-not $afterMap.ContainsKey($order)) { $lost += $order }
    elseif ($beforeMap[$order] -ne $afterMap[$order]) { $changedDriver += [pscustomobject]@{ orderId = $order; before = $beforeMap[$order]; after = $afterMap[$order] } }
  }
  $sequenceChanged = @()
  $appendOnlyExtensions = @()
  foreach ($route in @($Before.routes)) {
    $match = @($After.routes | Where-Object { $_.driverId -eq $route.driverId }) | Select-Object -First 1
    if ($match -and $match.sequence -ne $route.sequence) {
      if ($match.sequence.StartsWith($route.sequence)) {
        $appendOnlyExtensions += [pscustomobject]@{ driverId = $route.driverId; before = $route.sequence; after = $match.sequence }
      } else {
        $sequenceChanged += [pscustomobject]@{ driverId = $route.driverId; before = $route.sequence; after = $match.sequence }
      }
    }
  }
  [pscustomobject]@{ lostOrders = $lost; changedDriver = $changedDriver; sequenceChanged = $sequenceChanged; appendOnlyExtensions = $appendOnlyExtensions }
}

$drivers = @(
  @{ driverId = "DRV_CHURN_A"; lat = 10.77220; lng = 106.66460; capacity = 100; currentLoad = 0; status = "IDLE" },
  @{ driverId = "DRV_CHURN_B"; lat = 10.80120; lng = 106.71140; capacity = 100; currentLoad = 0; status = "IDLE" },
  @{ driverId = "DRV_CHURN_C"; lat = 10.75050; lng = 106.68010; capacity = 100; currentLoad = 0; status = "IDLE" }
)

$baseOrders = @(
  @{ orderId = "ORD_CHURN_001"; pickupLat = 10.77550; pickupLng = 106.66820; dropoffLat = 10.78110; dropoffLng = 106.69050; demand = 4; deadlineMinutes = 80 },
  @{ orderId = "ORD_CHURN_002"; pickupLat = 10.77920; pickupLng = 106.67680; dropoffLat = 10.79280; dropoffLng = 106.70420; demand = 6; deadlineMinutes = 90 },
  @{ orderId = "ORD_CHURN_003"; pickupLat = 10.80420; pickupLng = 106.71580; dropoffLat = 10.78880; dropoffLng = 106.70120; demand = 5; deadlineMinutes = 75 }
)

$newOrders = @(
  @{ orderId = "ORD_CHURN_004"; pickupLat = 10.77640; pickupLng = 106.67010; dropoffLat = 10.78320; dropoffLng = 106.69380; demand = 3; deadlineMinutes = 85 },
  @{ orderId = "ORD_CHURN_005"; pickupLat = 10.80270; pickupLng = 106.71370; dropoffLat = 10.79120; dropoffLng = 106.70680; demand = 3; deadlineMinutes = 70 }
)

$session = Invoke-Irx "/v1/live/sessions" "POST" @{
  requestId = "churn-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"
  tenantId = "demo"
  cityId = "hcm"
  profile = "LIVE_ROLLING"
  drivers = $drivers
  rollingConfig = @{ freezeNextStop = $true; freezePickedOrders = $true; adaptiveMlMode = "TOP_K_ASSISTED" }
}

foreach ($order in $baseOrders) { Add-Order $session.sessionId $order }
$cycle1 = Run-Cycle $session.sessionId "base-route"
$snap1 = Capture "after-cycle-1" $session.sessionId $cycle1
Start-Sleep -Milliseconds $DelayMs
$snap1Tick = Capture "after-cycle-1-tick" $session.sessionId

Add-Order $session.sessionId $newOrders[0]
$before2 = Capture "before-cycle-2" $session.sessionId
$cycle2 = Run-Cycle $session.sessionId "insert-order-4"
$snap2 = Capture "after-cycle-2" $session.sessionId $cycle2
Start-Sleep -Milliseconds $DelayMs
$snap2Tick = Capture "after-cycle-2-tick" $session.sessionId

Add-Order $session.sessionId $newOrders[1]
$before3 = Capture "before-cycle-3" $session.sessionId
$cycle3 = Run-Cycle $session.sessionId "insert-order-5"
$snap3 = Capture "after-cycle-3" $session.sessionId $cycle3

$comparisons = [pscustomobject]@{
  cycle1ToCycle2 = Compare-Routes $snap1 $snap2
  cycle2ToCycle3 = Compare-Routes $snap2 $snap3
}

$rootCauses = @()
if (@($comparisons.cycle1ToCycle2.lostOrders).Count -gt 0 -or @($comparisons.cycle2ToCycle3.lostOrders).Count -gt 0) { $rootCauses += "LAST_RESULT_REPLACED_ACTIVE_ROUTE" }
if (@($comparisons.cycle1ToCycle2.changedDriver).Count -gt 0 -or @($comparisons.cycle2ToCycle3.changedDriver).Count -gt 0) { $rootCauses += "ORDER_DRIVER_NOT_STICKY" }
if (@($comparisons.cycle1ToCycle2.sequenceChanged).Count -gt 0 -or @($comparisons.cycle2ToCycle3.sequenceChanged).Count -gt 0) { $rootCauses += "NO_FREEZE_NEXT_STOP_OR_ROUTE_REORDERED" }
if ($cycle2.routeChurnPercent -and "$($cycle2.routeChurnPercent)" -ne "0.0%") { $rootCauses += "BACKEND_REPORTS_ROUTE_CHURN_CYCLE_2" }
if ($cycle3.routeChurnPercent -and "$($cycle3.routeChurnPercent)" -ne "0.0%") { $rootCauses += "BACKEND_REPORTS_ROUTE_CHURN_CYCLE_3" }
if (-not $rootCauses.Count) { $rootCauses += "NO_CHURN_REPRODUCED_IN_API_CHECK_FE_AUTO_CYCLE_OR_RENDER" }

$timeline = @($snap1, $snap1Tick, $before2, $snap2, $snap2Tick, $before3, $snap3)
$summary = [pscustomobject]@{
  gate = "live-route-churn-root-cause"
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  rootCauses = $rootCauses
  cycle1Churn = $cycle1.routeChurnPercent
  cycle2Churn = $cycle2.routeChurnPercent
  cycle3Churn = $cycle3.routeChurnPercent
  comparisons = $comparisons
  timelineCompact = @($timeline | ForEach-Object { [pscustomobject]@{ label=$_.label; bufferedOrders=$_.bufferedOrders; assignedOrders=$_.assignedOrders; routeChurnPercent=$_.routeChurnPercent; routes=$_.routes; drivers=$_.drivers } })
  overallPass = ($rootCauses.Count -eq 1 -and $rootCauses[0] -eq "NO_CHURN_REPRODUCED_IN_API_CHECK_FE_AUTO_CYCLE_OR_RENDER")
}

$timelinePath = Join-Path $OutputDir "route-churn-timeline.json"
$summaryPath = Join-Path $OutputDir "route-churn-summary.json"
$timeline | ConvertTo-Json -Depth 100 | Set-Content $timelinePath -Encoding UTF8
$summary | ConvertTo-Json -Depth 100 | Set-Content $summaryPath -Encoding UTF8
Write-Output "TIMELINE=$timelinePath"
Write-Output "SUMMARY=$summaryPath"
Write-Output "ROOT_CAUSES=$($rootCauses -join ',')"
if (-not $summary.overallPass) { exit 1 }
