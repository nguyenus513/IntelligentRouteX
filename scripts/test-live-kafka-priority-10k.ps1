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
    $urgent = ($i % 25) -eq 0
    $priority = if ($urgent) { 10 } elseif (($i % 7) -eq 0) { 5 } else { 1 }
    $eta = if ($urgent) { 15 } elseif ($priority -eq 5) { 25 } else { 45 }
    $body = @{
        tenantId = "demo"
        regionId = if (($i % 2) -eq 0) { "hcmc-east" } else { "hcmc-west" }
        externalOrderId = "LIVE-P-$i"
        pickupLat = 10.75
        pickupLng = 106.67
        dropoffLat = 10.76
        dropoffLng = 106.68
        urgent = $urgent
        priority = $priority
        promisedEtaMinutes = $eta
    } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post "$BaseUrl/live/orders" -ContentType "application/json" -Body $body -TimeoutSec 5 | Out-Null
}

for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 1
    $state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
    $accepted = [int]$state.data.acceptedOrders
    $assigned = [int]$state.data.assignedOrders
    $buffered = [int]$state.data.bufferedOrders
    if (($accepted - $baseAccepted) -ge $Orders -and ($assigned - $baseAssigned) -ge $Orders -and $buffered -eq 0) { break }
}
$watch.Stop()

$state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$events = Invoke-RestMethod "$BaseUrl/live/events?limit=1000" -TimeoutSec 10
$cycles = @($events.data.items | Where-Object { $_.type -eq "LIVE_CYCLE_COMPLETED" })

[pscustomobject]@{
    ok = $true
    orders = $Orders
    transport = $state.data.transport
    acceptedOrders = $state.data.acceptedOrders
    assignedOrders = $state.data.assignedOrders
    acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    bufferedOrders = $state.data.bufferedOrders
    completedCycles = $state.data.completedCycles
    visibleCycleEvents = $cycles.Count
    urgentCycles = @($cycles | Where-Object { [int]$_.data.urgentCount -gt 0 }).Count
    avgBatchSize = [math]::Round((($cycles | ForEach-Object { [int]$_.data.assigned }) | Measure-Object -Average).Average, 2)
    maxPrioritySeen = (($cycles | ForEach-Object { [int]$_.data.maxPriority }) | Measure-Object -Maximum).Maximum
    elapsedMs = $watch.ElapsedMilliseconds
} | ConvertTo-Json -Depth 8
