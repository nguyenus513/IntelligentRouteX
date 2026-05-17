param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/events")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Tenant-Id"="demo";"X-Api-Key"="demo-key"}
$s=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/live/sessions" -Headers $headers -ContentType "application/json" -Body (@{requestId="evt";tenantId="demo"}|ConvertTo-Json)
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/live/sessions/$($s.sessionId)/orders" -Headers $headers -ContentType "application/json" -Body (@{requestId="evt-o";tenantId="demo";order=@{orderId="EVT-1"}}|ConvertTo-Json -Depth 5)|Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/live/sessions/$($s.sessionId)/cycles" -Headers $headers -ContentType "application/json" -Body (@{requestId="evt-c";tenantId="demo"}|ConvertTo-Json) -TimeoutSec 420|Out-Null
$events=(Invoke-WebRequest -Uri "$BaseUrl/v1/live/sessions/$($s.sessionId)/events" -UseBasicParsing -TimeoutSec 30).Content
$pass=$events -match "ORDER_BUFFERED" -and $events -match "CYCLE_COMPLETED" -and $events -match "ROUTE_UPDATED"
$summary=[pscustomobject]@{gate="api-event-stream";overallPass=$pass;sessionId=$s.sessionId;events=$events}
$path=Join-Path $OutputDir "api-event-stream-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
