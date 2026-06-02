param(
    [string]$BaseUrl = "http://localhost:18116/api/v1",
    [int]$Orders = 10000,
    [int]$Clusters = 4
)

$ErrorActionPreference = "Stop"

Invoke-RestMethod -Method Post "$BaseUrl/live/start" -TimeoutSec 5 | Out-Null
$baseline = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$baseAccepted = [int]$baseline.data.acceptedOrders
$baseAssigned = [int]$baseline.data.assignedOrders
$baseCycles = [int]$baseline.data.completedCycles

$clusterCenters = @(
    @{ region = "hcmc-north"; pLat = 10.82; pLng = 106.68; dLat = 10.84; dLng = 106.70; eta = 35 },
    @{ region = "hcmc-east";  pLat = 10.78; pLng = 106.75; dLat = 10.80; dLng = 106.78; eta = 30 },
    @{ region = "hcmc-west";  pLat = 10.75; pLng = 106.61; dLat = 10.77; dLng = 106.63; eta = 40 },
    @{ region = "hcmc-south"; pLat = 10.70; pLng = 106.66; dLat = 10.72; dLng = 106.68; eta = 45 }
)

$watch = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 1; $i -le $Orders; $i++) {
    $cluster = $clusterCenters[($i - 1) % [math]::Min($Clusters, $clusterCenters.Count)]
    $jitter = (($i % 11) - 5) * 0.001
    $urgent = ($i % 50) -eq 0
    $priority = if ($urgent) { 10 } elseif (($i % 9) -eq 0) { 6 } else { 2 }
    $body = @{
        tenantId = "demo"
        regionId = $cluster.region
        externalOrderId = "LIVE-SIM-$i"
        pickupLat = [double]$cluster.pLat + $jitter
        pickupLng = [double]$cluster.pLng + $jitter
        dropoffLat = [double]$cluster.dLat + $jitter
        dropoffLng = [double]$cluster.dLng + $jitter
        urgent = $urgent
        priority = $priority
        promisedEtaMinutes = if ($urgent) { 15 } else { [int]$cluster.eta }
    } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post "$BaseUrl/live/orders" -ContentType "application/json" -Body $body -TimeoutSec 5 | Out-Null
}

for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 1
    $state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
    $acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    $assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    if ($acceptedDelta -ge $Orders -and $assignedDelta -ge $Orders -and [int]$state.data.bufferedOrders -eq 0) { break }
}
$watch.Stop()

$state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$events = Invoke-RestMethod "$BaseUrl/live/events?limit=1000" -TimeoutSec 10
$cycles = @($events.data.items | Where-Object { $_.type -eq "LIVE_CYCLE_COMPLETED" -and [int]($_.data.cycleId -replace '\D','') -gt $baseCycles })
$similarities = @($cycles | Where-Object { $null -ne $_.data.avgSimilarity } | ForEach-Object { [double]$_.data.avgSimilarity })
$assigned = @($cycles | ForEach-Object { [int]$_.data.assigned })

[pscustomobject]@{
    ok = $true
    scenario = "clustered-similarity"
    orders = $Orders
    clusters = $Clusters
    transport = $state.data.transport
    acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    bufferedOrders = $state.data.bufferedOrders
    completedCyclesDelta = [int]$state.data.completedCycles - $baseCycles
    visibleCycleEvents = $cycles.Count
    avgBatchSize = [math]::Round(($assigned | Measure-Object -Average).Average, 2)
    avgSimilarity = [math]::Round(($similarities | Measure-Object -Average).Average, 3)
    minSimilarity = [math]::Round(($similarities | Measure-Object -Minimum).Minimum, 3)
    elapsedMs = $watch.ElapsedMilliseconds
} | ConvertTo-Json -Depth 8
