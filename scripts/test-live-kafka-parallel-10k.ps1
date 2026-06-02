param(
    [string]$BaseUrl = "http://localhost:18116/api/v1",
    [int]$Orders = 10000,
    [int]$Parallelism = 200
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

Invoke-RestMethod -Method Post "$BaseUrl/live/start" -TimeoutSec 5 | Out-Null
$baseline = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
$baseAccepted = [int]$baseline.data.acceptedOrders
$baseAssigned = [int]$baseline.data.assignedOrders
$baseCycles = [int]$baseline.data.completedCycles

$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(20)
$url = "$BaseUrl/live/orders"
$watch = [System.Diagnostics.Stopwatch]::StartNew()

try {
    for ($offset = 1; $offset -le $Orders; $offset += $Parallelism) {
        $tasks = New-Object System.Collections.Generic.List[System.Threading.Tasks.Task[System.Net.Http.HttpResponseMessage]]
        $last = [math]::Min($Orders, $offset + $Parallelism - 1)
        for ($i = $offset; $i -le $last; $i++) {
            $cluster = $i % 4
            $urgent = (($i % 50) -eq 0).ToString().ToLowerInvariant()
            $priority = if (($i % 50) -eq 0) { 10 } elseif (($i % 9) -eq 0) { 6 } else { 2 }
            $eta = if (($i % 50) -eq 0) { 15 } elseif ($cluster -eq 0) { 30 } elseif ($cluster -eq 1) { 35 } elseif ($cluster -eq 2) { 40 } else { 45 }
            $lat = 10.70 + ($cluster * 0.04) + (($i % 7) * 0.001)
            $lng = 106.60 + ($cluster * 0.04) + (($i % 7) * 0.001)
            $region = @("hcmc-south", "hcmc-west", "hcmc-east", "hcmc-north")[$cluster]
            $json = "{`"tenantId`":`"demo`",`"regionId`":`"$region`",`"externalOrderId`":`"LIVE-PAR-$i`",`"pickupLat`":$lat,`"pickupLng`":$lng,`"dropoffLat`":$($lat + 0.02),`"dropoffLng`":$($lng + 0.02),`"urgent`":$urgent,`"priority`":$priority,`"promisedEtaMinutes`":$eta}"
            $content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, "application/json")
            $tasks.Add($client.PostAsync($url, $content))
        }
        [System.Threading.Tasks.Task]::WaitAll($tasks.ToArray())
        foreach ($task in $tasks) {
            if (-not $task.Result.IsSuccessStatusCode) { throw "POST failed: $($task.Result.StatusCode)" }
            $task.Result.Dispose()
        }
    }

    for ($i = 0; $i -lt 180; $i++) {
        Start-Sleep -Seconds 1
        $state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
        $acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
        $assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
        if ($acceptedDelta -ge $Orders -and $assignedDelta -ge $Orders -and [int]$state.data.bufferedOrders -eq 0) { break }
    }
} finally {
    $watch.Stop()
    $client.Dispose()
}

$state = Invoke-RestMethod "$BaseUrl/live/state" -TimeoutSec 5
[pscustomobject]@{
    ok = $true
    scenario = "parallel-clustered-similarity"
    orders = $Orders
    parallelism = $Parallelism
    transport = $state.data.transport
    acceptedDelta = [int]$state.data.acceptedOrders - $baseAccepted
    assignedDelta = [int]$state.data.assignedOrders - $baseAssigned
    bufferedOrders = $state.data.bufferedOrders
    completedCyclesDelta = [int]$state.data.completedCycles - $baseCycles
    avgBatchSizeGlobal = $state.data.avgBatchSize
    maxBatchSizeGlobal = $state.data.maxBatchSize
    avgSimilarityGlobal = $state.data.avgSimilarity
    elapsedMs = $watch.ElapsedMilliseconds
} | ConvertTo-Json -Depth 8
