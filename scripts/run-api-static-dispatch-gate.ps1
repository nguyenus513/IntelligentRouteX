param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/static")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Tenant-Id"="demo";"X-Api-Key"="demo-key"}
$body=@{requestId="static-001";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING";adaptiveMl=@{enabled=$true;mode="QUALITY_SEEKING";topKMoves=80;explorationRate=0.2;qualityBudgetMs=5000};options=@{maxRuntimeMs=25000;returnDiagnostics=$true}}|ConvertTo-Json -Depth 10
$job=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec 420
$status=Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)" -Headers $headers -TimeoutSec 60
$result=Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)/result" -Headers $headers -TimeoutSec 60
$pass=$status.status -eq "COMPLETED" -and $result.finalSolver -eq "IRX_ML_FUSED_HYBRID" -and $result.metrics.coverageRate -gt 0 -and $null -ne $result.diagnostics.adaptiveMlPolicy
$summary=[pscustomobject]@{gate="api-static-dispatch";overallPass=$pass;job=$job;status=$status;resultMetrics=$result.metrics;adaptiveMlPolicy=$result.diagnostics.adaptiveMlPolicy}
$path=Join-Path $OutputDir "api-static-dispatch-summary.json"; $summary|ConvertTo-Json -Depth 30|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
