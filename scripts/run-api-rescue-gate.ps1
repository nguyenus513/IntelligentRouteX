param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/rescue")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Tenant-Id"="demo";"X-Api-Key"="demo-key"}
$job=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/rescue/jobs" -Headers $headers -ContentType "application/json" -Body (@{requestId="rescue-001";tenantId="demo";reason="DRIVER_DELAYED";affectedDriverId="D01";affectedOrderIds=@("ORD-1");options=@{lateNotWorse=$true;maxRuntimeMs=5000}}|ConvertTo-Json -Depth 8) -TimeoutSec 420
$result=Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/rescue/jobs/$($job.jobId)/result" -Headers $headers -TimeoutSec 60
$pass=$job.status -eq "COMPLETED" -and $result.finalSolver -eq "IRX_ML_FUSED_HYBRID" -and $result.diagnostics.rescueDominanceGuard.passed -eq $true
$summary=[pscustomobject]@{gate="api-rescue";overallPass=$pass;job=$job;metrics=$result.metrics;rescueDominanceGuard=$result.diagnostics.rescueDominanceGuard}
$path=Join-Path $OutputDir "api-rescue-summary.json"; $summary|ConvertTo-Json -Depth 30|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
