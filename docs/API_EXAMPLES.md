# API Examples

Set variables:

```powershell
$BaseUrl = "http://localhost:18116/api/v1"
$Headers = @{ "X-Api-Key" = "demo-key" }
```

## Health

```powershell
Invoke-RestMethod "$BaseUrl/health" -Headers $Headers
```

## Static async job

```powershell
$body = @{ scenarioId="raw-s"; orders=@(); drivers=@(); policy=@{ adaptiveMlPolicyMode="QUALITY_SEEKING" } } | ConvertTo-Json -Depth 20
$job = Invoke-RestMethod -Method Post "$BaseUrl/static/dispatch/jobs" -Headers ($Headers + @{"Idempotency-Key"="demo-static-001"}) -ContentType application/json -Body $body
$jobId = $job.data.jobId
Invoke-RestMethod "$BaseUrl/jobs/$jobId" -Headers $Headers
Invoke-RestMethod "$BaseUrl/jobs/$jobId/result" -Headers $Headers
```

## Live rolling cycle

```powershell
Invoke-RestMethod -Method Post "$BaseUrl/live/start" -Headers $Headers -ContentType application/json -Body '{}'
Invoke-RestMethod -Method Post "$BaseUrl/live/orders" -Headers $Headers -ContentType application/json -Body '{"orderId":"ORD-LIVE-1"}'
Invoke-RestMethod -Method Post "$BaseUrl/live/drivers/location" -Headers $Headers -ContentType application/json -Body '{"driverId":"D1","lat":10.78,"lng":106.7}'
$cycle = Invoke-RestMethod -Method Post "$BaseUrl/live/cycles/run-now" -Headers $Headers -ContentType application/json -Body '{}'
Invoke-RestMethod "$BaseUrl/live/cycles/$($cycle.data.cycleId)/result" -Headers $Headers
Invoke-RestMethod "$BaseUrl/live/events" -Headers $Headers
```

## Rescue job

```powershell
$rescue = Invoke-RestMethod -Method Post "$BaseUrl/rescue/jobs" -Headers $Headers -ContentType application/json -Body '{"reason":"DRIVER_DELAYED"}'
Invoke-RestMethod "$BaseUrl/rescue/jobs/$($rescue.data.jobId)/result" -Headers $Headers
```

## BigData-lite batch and pagination

```powershell
$items = 1..1000 | ForEach-Object { @{ orderId="ORD-$_"; externalOrderId="EXT-$_"; lat=10.7; lng=106.7 } }
$body = @{ batchId="BATCH-001"; tenantId="demo"; items=$items; options=@{ validationMode="STRICT"; dedupeKey="externalOrderId" } } | ConvertTo-Json -Depth 30
Invoke-RestMethod -Method Post "$BaseUrl/bigdata/batches" -Headers $Headers -ContentType application/json -Body $body
Invoke-RestMethod "$BaseUrl/bigdata/batches/BATCH-001/items?page=0&size=50" -Headers $Headers
```

## Artifacts and events

```powershell
Invoke-RestMethod "$BaseUrl/artifacts" -Headers $Headers
Invoke-RestMethod "$BaseUrl/events?limit=20" -Headers $Headers
```
