param(
    [string]$BaseUrl = "http://localhost:18116/api/v1",
    [int]$Orders = 10000
)

$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 5
if (-not $health.ok) { throw "IRX API health failed" }

$items = 1..$Orders | ForEach-Object {
    $offset = ($_ % 100) * 0.0005
    @{
        externalOrderId = "CORE-$_"
        pickupLat = 10.75 + $offset
        pickupLng = 106.67 + $offset
        dropoffLat = 10.76 + $offset
        dropoffLng = 106.68 + $offset
        promisedEtaMinutes = 45
        regionId = "hcmc"
    }
}
$batchId = "CORE-$Orders-$(Get-Date -Format yyyyMMddHHmmss)"
$body = @{ batchId = $batchId; tenantId = "demo"; items = $items; options = @{ dedupeKey = "externalOrderId" } } | ConvertTo-Json -Depth 20 -Compress
$watch = [System.Diagnostics.Stopwatch]::StartNew()
$created = Invoke-RestMethod -Method Post "$BaseUrl/bigdata/batches" -ContentType "application/json" -Body $body -TimeoutSec 60
$jobId = $created.data.jobId

for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 2
    $status = Invoke-RestMethod "$BaseUrl/bigdata/batches/$batchId" -TimeoutSec 10
    if ($status.data.status -eq "COMPLETED") { break }
}
$watch.Stop()

$events = Invoke-RestMethod "$BaseUrl/jobs/$jobId/events?limit=1000" -TimeoutSec 10
$result = Invoke-RestMethod "$BaseUrl/jobs/$jobId/result" -TimeoutSec 10
$coreChunks = @($events.data.items | Where-Object { $_.type -eq "CORE_DISPATCH_CHUNK_COMPLETED" -and $_.data.core -eq $true }).Count
$fallbacks = @($events.data.items | Where-Object { $_.type -eq "CORE_DISPATCH_FALLBACK" }).Count

[pscustomobject]@{
    ok = $true
    batchId = $batchId
    jobId = $jobId
    orders = $Orders
    status = $result.data.status
    assignedOrders = $result.data.summary.assignedOrders
    routeCount = $result.data.summary.routeCount
    coreChunks = $coreChunks
    fallbackEvents = $fallbacks
    elapsedMs = $watch.ElapsedMilliseconds
} | ConvertTo-Json -Depth 8
