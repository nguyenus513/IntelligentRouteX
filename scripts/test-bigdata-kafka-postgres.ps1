param(
    [string]$BaseUrl = "http://localhost:18116/api/v1"
)

$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 5
if (-not $health.ok) { throw "IRX API health failed" }

$items = 1..250 | ForEach-Object { @{ externalOrderId = "KPG-$_"; value = $_ } }
$body = @{ batchId = "KPG-$(Get-Date -Format yyyyMMddHHmmss)"; tenantId = "demo"; items = $items; options = @{ dedupeKey = "externalOrderId" } } | ConvertTo-Json -Depth 20
$created = Invoke-RestMethod -Method Post "$BaseUrl/bigdata/batches" -ContentType "application/json" -Body $body -TimeoutSec 15
$jobId = $created.data.jobId

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $events = Invoke-RestMethod "$BaseUrl/jobs/$jobId/events?limit=200" -TimeoutSec 5
    $done = @($events.data.items | Where-Object { $_.type -eq "JOB_COMPLETED" }).Count
    if ($done -gt 0) { break }
}

$result = Invoke-RestMethod "$BaseUrl/jobs/$jobId/result" -TimeoutSec 5
$queues = Invoke-RestMethod "$BaseUrl/runtime/queues" -TimeoutSec 5

[pscustomobject]@{
    ok = $true
    jobId = $jobId
    createdStatus = $created.data.status
    resultStatus = $result.data.status
    assignedOrders = $result.data.summary.assignedOrders
    queueSummary = $queues.data._summary
} | ConvertTo-Json -Depth 8
