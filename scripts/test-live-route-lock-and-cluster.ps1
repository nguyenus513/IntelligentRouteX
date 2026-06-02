param(
    [string]$BaseUrl = "http://localhost:18116",
    [string]$OutputDir = "artifacts/test-reports/live-route-lock-cluster",
    [switch]$AllowSyntheticRouting
)

$ErrorActionPreference = "Stop"
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function PostJson($Path, $Body) {
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl$Path" -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30)
    } catch {
        $bodyText = ""
        try { $bodyText = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {}
        throw "POST_FAILED path=$Path status=$($_.Exception.Response.StatusCode.value__) body=$bodyText"
    }
}

function GetJson($Path) {
    Invoke-RestMethod -Method Get -Uri "$BaseUrl$Path" -Headers $headers
}

function SaveJson($Name, $Value) {
    $Value | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -Path (Join-Path $OutputDir $Name)
}

function Assert($Condition, $Message) {
    if (-not $Condition) { throw "ASSERT_FAILED: $Message" }
}

function StopKey($Stop) {
    if (-not $Stop.orderId) { return $null }
    return "$($Stop.type):$($Stop.orderId)"
}

function SnapshotAssignments($State) {
    $map = @{}
    foreach ($route in @($State.activeRoutes)) {
        foreach ($stop in @($route.stops)) {
            if ($stop.orderId) {
                if (-not $map.ContainsKey($stop.orderId)) {
                    $map[$stop.orderId] = [ordered]@{ driverId = $route.driverId; stops = @(); routeId = $route.routeId }
                }
                $map[$stop.orderId].stops += @(StopKey $stop)
            }
        }
    }
    return $map
}

function RouteSequences($State) {
    $map = @{}
    foreach ($route in @($State.activeRoutes)) {
        $map[$route.driverId] = @($route.stops | Where-Object { $_.orderId } | ForEach-Object { StopKey $_ })
    }
    return $map
}

function ContainsSubsequence($Before, $After) {
    $cursor = 0
    foreach ($item in $After) {
        if ($cursor -lt $Before.Count -and $item -eq $Before[$cursor]) { $cursor++ }
    }
    return $cursor -eq $Before.Count
}

function Km($A, $B) {
    $earth = 6371.0
    $dLat = ([double]$B.lat - [double]$A.lat) * [Math]::PI / 180.0
    $dLng = ([double]$B.lng - [double]$A.lng) * [Math]::PI / 180.0
    $lat1 = [double]$A.lat * [Math]::PI / 180.0
    $lat2 = [double]$B.lat * [Math]::PI / 180.0
    $x = [Math]::Sin($dLat / 2.0) * [Math]::Sin($dLat / 2.0) + [Math]::Cos($lat1) * [Math]::Cos($lat2) * [Math]::Sin($dLng / 2.0) * [Math]::Sin($dLng / 2.0)
    return 2.0 * $earth * [Math]::Atan2([Math]::Sqrt($x), [Math]::Sqrt(1.0 - $x))
}

function AssertRouteGeometryCoversStops($State, $Label) {
    foreach ($route in @($State.activeRoutes)) {
        Assert ($route.geometryMode -eq 'ROAD_ROUTE') "$Label route $($route.routeId) is not ROAD_ROUTE"
        Assert (@($route.polyline).Count -ge 2) "$Label route $($route.routeId) missing polyline"
        foreach ($stop in @($route.stops | Where-Object { $_.orderId })) {
            $nearest = 999999.0
            foreach ($point in @($route.polyline)) { $nearest = [Math]::Min($nearest, (Km $stop $point)) }
            Assert ($nearest -le 0.18) "$Label stop $($stop.type):$($stop.orderId) not covered by route $($route.routeId), nearestKm=$nearest"
        }
    }
}

$drivers = @(
    @{ driverId = "DRV_LOCK_A"; lat = 10.77670; lng = 106.70090; capacity = 100; speedKmh = 28 },
    @{ driverId = "DRV_LOCK_B"; lat = 10.78910; lng = 106.70420; capacity = 100; speedKmh = 30 },
    @{ driverId = "DRV_LOCK_C"; lat = 10.75880; lng = 106.66640; capacity = 100; speedKmh = 26 }
)

$baseOrders = @(
    @{ orderId = "LOCK_BASE_001"; pickupLat = 10.77720; pickupLng = 106.70080; dropoffLat = 10.78120; dropoffLng = 106.70720; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_BASE_002"; pickupLat = 10.77830; pickupLng = 106.69980; dropoffLat = 10.78340; dropoffLng = 106.70930; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_BASE_003"; pickupLat = 10.78780; pickupLng = 106.70450; dropoffLat = 10.79200; dropoffLng = 106.71000; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_BASE_004"; pickupLat = 10.78900; pickupLng = 106.70560; dropoffLat = 10.79480; dropoffLng = 106.71140; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_BASE_005"; pickupLat = 10.75920; pickupLng = 106.66690; dropoffLat = 10.76480; dropoffLng = 106.67220; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_BASE_006"; pickupLat = 10.76040; pickupLng = 106.66780; dropoffLat = 10.76610; dropoffLng = 106.67360; demand = 1; deadlineMinutes = 80 }
)

$newOrders = @(
    @{ orderId = "LOCK_NEW_007"; pickupLat = 10.77100; pickupLng = 106.69210; dropoffLat = 10.77570; dropoffLng = 106.69910; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_NEW_008"; pickupLat = 10.77220; pickupLng = 106.69340; dropoffLat = 10.77680; dropoffLng = 106.70060; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_NEW_009"; pickupLat = 10.79120; pickupLng = 106.69820; dropoffLat = 10.79700; dropoffLng = 106.70410; demand = 1; deadlineMinutes = 80 },
    @{ orderId = "LOCK_NEW_010"; pickupLat = 10.75420; pickupLng = 106.68180; dropoffLat = 10.76000; dropoffLng = 106.68820; demand = 1; deadlineMinutes = 80 }
)

try {
    Invoke-RestMethod -Method Get -Uri "$BaseUrl/actuator/health" | Out-Null
} catch {
    Write-Host "[LIVE_LOCK_GATE] Backend offline at $BaseUrl"
    exit 2
}

$session = PostJson "/v1/live/sessions" @{ requestId = "lock-gate-session"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers; rollingConfig = @{ cycleIntervalSeconds = 3; maxBufferWaitSeconds = 15; maxRuntimeMsPerCycle = 5000; adaptiveMlMode = "TOP_K_ASSISTED"; freezeNextStop = $true; freezePickedOrders = $true } }
$sid = $session.sessionId
Write-Host "[LIVE_LOCK_GATE] session=$sid"

foreach ($order in $baseOrders) { PostJson "/v1/live/sessions/$sid/orders" @{ requestId = "add-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null }
$preCycleState = GetJson "/v1/live/sessions/$sid/state"
SaveJson "00-pre-cycle-state.json" $preCycleState
$preClusters = @($preCycleState.decisionTrace.clusterSelection)
Assert ($preClusters.Count -ge 1) "realtime cluster missing before first cycle"
Assert ((@($preClusters[0].orderIds).Count -ge 3) -or ($preClusters.Count -ge 2)) "realtime cluster too small before first cycle"

$cycle1 = PostJson "/v1/live/sessions/$sid/cycles" @{ requestId = "lock-gate-cycle-1"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "TOP_K_ASSISTED" }
$state1 = GetJson "/v1/live/sessions/$sid/state"
SaveJson "01-cycle.json" $cycle1
SaveJson "01-state.json" $state1
Assert (@($state1.activeRoutes).Count -gt 0) "cycle1 activeRoutes empty"
AssertRouteGeometryCoversStops $state1 "cycle1"
$assign1 = SnapshotAssignments $state1
$seq1 = RouteSequences $state1
foreach ($order in $baseOrders) { Assert ($assign1.ContainsKey($order.orderId)) "cycle1 missing assigned base order $($order.orderId)" }

foreach ($order in $newOrders) { PostJson "/v1/live/sessions/$sid/orders" @{ requestId = "add-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null }
$stateBefore2 = GetJson "/v1/live/sessions/$sid/state"
SaveJson "02-before-cycle-state.json" $stateBefore2

$cycle2 = PostJson "/v1/live/sessions/$sid/cycles" @{ requestId = "lock-gate-cycle-2"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "TOP_K_ASSISTED" }
$state2 = GetJson "/v1/live/sessions/$sid/state"
SaveJson "02-cycle.json" $cycle2
SaveJson "02-state.json" $state2
$assign2 = SnapshotAssignments $state2
$seq2 = RouteSequences $state2
AssertRouteGeometryCoversStops $state2 "cycle2"

foreach ($order in $baseOrders) {
    $id = $order.orderId
    Assert ($assign2.ContainsKey($id)) "cycle2 lost locked order $id"
    Assert ($assign2[$id].driverId -eq $assign1[$id].driverId) "cycle2 reassigned locked order $id from $($assign1[$id].driverId) to $($assign2[$id].driverId)"
}

foreach ($driverId in $seq1.Keys) {
    Assert ($seq2.ContainsKey($driverId)) "cycle2 lost route for driver $driverId"
    Assert (ContainsSubsequence @($seq1[$driverId]) @($seq2[$driverId])) "cycle2 reordered locked route for driver $driverId"
}

$clusters2 = @($state2.decisionTrace.clusterSelection)
Assert ($clusters2.Count -ge 1) "state2 cluster missing"
$multiClusters = @($clusters2 | Where-Object { @($_.orderIds).Count -gt 1 })
Assert ($multiClusters.Count -ge 1) "state2 clusters are singleton only"

$summary = [ordered]@{
    sessionId = $sid
    cycle1Routes = @($state1.activeRoutes).Count
    cycle2Routes = @($state2.activeRoutes).Count
    lockedBaseOrders = $baseOrders.Count
    clusterCount = $clusters2.Count
    maxClusterSize = (($clusters2 | ForEach-Object { @($_.orderIds).Count }) | Measure-Object -Maximum).Maximum
    routeLockPolicy = $state2.decisionTrace.routeLockPolicy.policy
    verdict = "PASS"
}
SaveJson "summary.json" $summary
Write-Host "[LIVE_LOCK_GATE] PASS routes=$($summary.cycle2Routes) clusters=$($summary.clusterCount) maxCluster=$($summary.maxClusterSize)"
