param(
    [string]$BaseUrl = "http://localhost:18116/api/v1",
    [int]$Orders = 10000
)

$ErrorActionPreference = "Stop"

Invoke-RestMethod -Method Post "$BaseUrl/live/start" -TimeoutSec 5 | Out-Null
$baseline = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$baseAccepted = [int]$baseline.data.acceptedOrders
$baseAssigned = [int]$baseline.data.assignedOrders

$watch = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 1; $i -le $Orders; $i++) {
    $body = @{
        tenantId = "demo"
        regionId = "hcmc"
        externalOrderId = "LIVE-$i"
        pickupLat = 10.75
        pickupLng = 106.67
        dropoffLat = 10.76
        dropoffLng = 106.68
    } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post "$BaseUrl/live/orders" -ContentType "application/json" -Body $body -TimeoutSec 5 | Out-Null
}

for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    $state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
    $acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    $assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    if ($acceptedDelta -ge $Orders -and $assignedDelta -ge $Orders -and [int]$state.data.bufferedOrders -eq 0) { break }
}
$watch.Stop()

$state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$events = Invoke-RestMethod "$BaseUrl/live/events?limit=1000" -TimeoutSec 10
$cycleEvents = @($events.data.items | Where-Object { $_.type -eq "LIVE_CYCLE_COMPLETED" }).Count

[pscustomobject]@{
    ok = $true
    orders = $Orders
    transport = $state.data.transport
    acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    bufferedOrders = $state.data.bufferedOrders
    completedCycles = $state.data.completedCycles
    cycleEvents = $cycleEvents
    elapsedMs = $watch.ElapsedMilliseconds
} | ConvertTo-Json -Depth 8
