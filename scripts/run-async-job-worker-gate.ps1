param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/async-worker")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Tenant-Id"="demo";"X-Api-Key"="demo-key"}
$job=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $headers -ContentType "application/json" -Body (@{requestId="async-001";tenantId="demo";datasetId="raw-s";adaptiveMl=@{mode="QUALITY_SEEKING";topKMoves=80;explorationRate=0.2;qualityBudgetMs=5000}}|ConvertTo-Json -Depth 8) -TimeoutSec 420
$status=Invoke-RestMethod -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)" -Headers $headers
$result=Invoke-RestMethod -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)/result" -Headers $headers
$pass=$status.status -eq "COMPLETED" -and $result.finalSolver -eq "IRX_ML_FUSED_HYBRID" -and $null -ne $result.diagnostics
$summary=[pscustomobject]@{gate="async-worker";overallPass=$pass;job=$job;status=$status;metrics=$result.metrics;diagnosticsPresent=($null -ne $result.diagnostics)}
$path=Join-Path $OutputDir "async-worker-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
