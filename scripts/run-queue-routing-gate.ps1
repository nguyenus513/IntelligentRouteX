param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/queue")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Api-Key"="demo-key"}
$q=Invoke-RestMethod -Uri "$BaseUrl/v1/admin/queues" -Headers $headers
$pass=$q.status -eq "UP" -and $q.priority[0] -eq "RESCUE" -and $q.priority[1] -eq "LIVE" -and $q.priority[2] -eq "FAST" -and $null -ne $q.queueDepthByLane
$summary=[pscustomobject]@{gate="queue-routing";overallPass=$pass;queues=$q;rescueLane="RESCUE";liveLane="LIVE";qualityLane="QUALITY";benchmarkLane="BENCHMARK"}
$path=Join-Path $OutputDir "queue-routing-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
