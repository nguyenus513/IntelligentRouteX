param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/rate-limit")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$headers=@{"X-Tenant-Id"="burst";"X-Api-Key"="demo-key"}
$limited=$false
for($i=1;$i -le 25;$i++){ try{ Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers $headers -ContentType "application/json" -Body (@{requestId="burst-$i";tenantId="burst";datasetId="raw-s"}|ConvertTo-Json) -TimeoutSec 420|Out-Null } catch { if([int]$_.Exception.Response.StatusCode.value__ -eq 429){$limited=$true; break}else{throw} } }
$normal=Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/health"
$pass=$limited -and $normal.status -eq "ok"
$summary=[pscustomobject]@{gate="api-rate-limit";overallPass=$pass;rateLimited=$limited;normalHealth=$normal.status}
$path=Join-Path $OutputDir "api-rate-limit-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
