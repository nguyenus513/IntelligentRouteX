param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/dashboard-playground")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$health=Invoke-RestMethod "$BaseUrl/v1/health"
$version=Invoke-RestMethod "$BaseUrl/v1/version"
$pass=$health.status -eq "ok" -and $version.apiVersion -eq "v1"
$summary=[pscustomobject]@{gate="dashboard-api-playground";overallPass=$pass;health=$health;version=$version;note="API playground backend endpoints ready; dashboard can call /v1 facade"}
$path=Join-Path $OutputDir "dashboard-playground-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"; if(-not $pass){exit 1}
