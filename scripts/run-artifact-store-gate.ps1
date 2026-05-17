param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/artifacts")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$a=@{"X-Tenant-Id"="art-a";"X-Api-Key"="demo-key"}; $b=@{"X-Tenant-Id"="art-b";"X-Api-Key"="demo-key"}
$job=Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $a -ContentType "application/json" -Body (@{requestId="artifact-001";tenantId="art-a";datasetId="raw-s"}|ConvertTo-Json) -TimeoutSec 420
Invoke-RestMethod -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)/result" -Headers $a | Out-Null
$list=Invoke-RestMethod -Uri "$BaseUrl/v1/dispatch/jobs/$($job.jobId)/artifacts" -Headers $a
$artifact=$list[0]
$own=Invoke-RestMethod -Uri "$BaseUrl/v1/artifacts/$($artifact.artifactId)" -Headers $a
$cross=0; try{ Invoke-RestMethod -Uri "$BaseUrl/v1/artifacts/$($artifact.artifactId)" -Headers $b|Out-Null }catch{ $cross=[int]$_.Exception.Response.StatusCode.value__ }
$missing=0; try{ Invoke-RestMethod -Uri "$BaseUrl/v1/artifacts/art_missing" -Headers $a|Out-Null }catch{ $missing=[int]$_.Exception.Response.StatusCode.value__ }
$pass=$own.artifactId -eq $artifact.artifactId -and $cross -eq 403 -and $missing -eq 404
$summary=[pscustomobject]@{gate="artifact-store";overallPass=$pass;ownRead=200;crossTenantStatus=$cross;missingStatus=$missing;artifact=$artifact}
$path=Join-Path $OutputDir "artifact-store-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
