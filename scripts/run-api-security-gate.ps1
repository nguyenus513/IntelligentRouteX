param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/security")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$demo=@{"X-Tenant-Id"="demo";"X-Api-Key"="demo-key"}; $other=@{"X-Tenant-Id"="other";"X-Api-Key"="demo-key"}
function StatusOf($script){ try{ & $script; return 200 } catch { return [int]$_.Exception.Response.StatusCode.value__ } }
$body=@{requestId="idem-001";tenantId="demo";datasetId="raw-s";adaptiveMl=@{mode="QUALITY_SEEKING";topKMoves=80;explorationRate=0.2;qualityBudgetMs=5000}}|ConvertTo-Json -Depth 8
$job1=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $demo -ContentType "application/json" -Body $body -TimeoutSec 420
$job2=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $demo -ContentType "application/json" -Body $body -TimeoutSec 420
$conflictBody=@{requestId="idem-001";tenantId="demo";datasetId="raw-m"}|ConvertTo-Json
$conflict=StatusOf { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $demo -ContentType "application/json" -Body $conflictBody -TimeoutSec 60 | Out-Null }
$badLat=StatusOf { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $demo -ContentType "application/json" -Body (@{requestId="bad-lat";tenantId="demo";orders=@(@{orderId="bad";pickupLat=999;pickupLng=106;dropoffLat=10;dropoffLng=106;deadlineMinutes=10})}|ConvertTo-Json -Depth 8) | Out-Null }
$badDeadline=StatusOf { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $demo -ContentType "application/json" -Body (@{requestId="bad-deadline";tenantId="demo";orders=@(@{orderId="bad2";pickupLat=10;pickupLng=106;dropoffLat=10;dropoffLng=106;readyTimeMinutes=20;deadlineMinutes=10})}|ConvertTo-Json -Depth 8) | Out-Null }
$noKey=StatusOf { Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/dispatch/jobs/$($job1.jobId)" -Headers @{"X-Tenant-Id"="demo"} | Out-Null }
$cross=StatusOf { Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/dispatch/jobs/$($job1.jobId)" -Headers $other | Out-Null }
$sess=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/live/sessions" -Headers $demo -ContentType "application/json" -Body (@{requestId="sec-live";tenantId="demo"}|ConvertTo-Json)
$crossLive=StatusOf { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/live/sessions/$($sess.sessionId)/orders" -Headers $other -ContentType "application/json" -Body (@{requestId="x";tenantId="other";order=@{orderId="x"}}|ConvertTo-Json -Depth 5) | Out-Null }
$pass=$job1.jobId -eq $job2.jobId -and $conflict -eq 409 -and $badLat -eq 400 -and $badDeadline -eq 400 -and $noKey -eq 401 -and $cross -eq 403 -and $crossLive -eq 403
$summary=[pscustomobject]@{gate="api-security-idempotency-validation";overallPass=$pass;duplicateSameJob=($job1.jobId -eq $job2.jobId);conflictStatus=$conflict;badLatStatus=$badLat;badDeadlineStatus=$badDeadline;noKeyStatus=$noKey;crossTenantJobStatus=$cross;crossTenantLiveStatus=$crossLive}
$path=Join-Path $OutputDir "api-security-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
