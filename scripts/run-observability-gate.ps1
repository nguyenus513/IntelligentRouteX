param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/observability")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Api-Key"="demo-key"}
$health=Invoke-RestMethod "$BaseUrl/v1/health"
$version=Invoke-RestMethod "$BaseUrl/v1/version"
$queues=Invoke-RestMethod "$BaseUrl/v1/admin/queues" -Headers $headers
$workers=Invoke-RestMethod "$BaseUrl/v1/admin/workers" -Headers $headers
$metrics=Invoke-RestMethod "$BaseUrl/v1/admin/metrics" -Headers $headers
$pass=$health.status -eq "ok" -and $version.engineVersion -match "v0.9.9" -and $null -ne $queues.queueDepthByLane -and $null -ne $workers.workers -and $null -ne $metrics.adaptiveQualityGainCount -and $null -ne $metrics.rateLimitHits
$summary=[pscustomobject]@{gate="observability";overallPass=$pass;health=$health;version=$version;queues=$queues;workers=$workers;metrics=$metrics}
$path=Join-Path $OutputDir "observability-summary.json"; $summary|ConvertTo-Json -Depth 30|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
