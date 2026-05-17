# IRX API Examples

## Static async job

```powershell
$body = @{ scenarioId="raw-s"; orders=@(); drivers=@(); policy=@{ adaptiveMlPolicyMode="QUALITY_SEEKING" } } | ConvertTo-Json -Depth 20
Invoke-RestMethod -Method Post http://localhost:18116/api/v1/static/dispatch/jobs -Headers @{"Idempotency-Key"="demo-static-001"} -ContentType application/json -Body $body
```

## BigData-lite batch

```powershell
$items = 1..1000 | ForEach-Object { @{ orderId="ORD-$_"; externalOrderId="EXT-$_" } }
$body = @{ batchId="BATCH-001"; tenantId="demo"; items=$items; options=@{ validationMode="STRICT"; dedupeKey="externalOrderId" } } | ConvertTo-Json -Depth 30
Invoke-RestMethod -Method Post http://localhost:18116/api/v1/bigdata/batches -Headers @{"X-Api-Key"="demo-key"} -ContentType application/json -Body $body
```

## Live cycle

```powershell
Invoke-RestMethod -Method Post http://localhost:18116/api/v1/live/start
Invoke-RestMethod -Method Post http://localhost:18116/api/v1/live/orders -ContentType application/json -Body '{"orderId":"ORD-LIVE-1"}'
Invoke-RestMethod -Method Post http://localhost:18116/api/v1/live/cycles/run-now
```
