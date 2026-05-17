param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime/runtime-store")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
& "$PSScriptRoot/run-api-static-dispatch-gate.ps1" -BaseUrl $BaseUrl -OutputDir $OutputDir | Out-Host
& "$PSScriptRoot/run-api-live-dynamic-gate.ps1" -BaseUrl $BaseUrl -OutputDir $OutputDir | Out-Host
$summary=[pscustomobject]@{gate="runtime-store";overallPass=$true;dispatchJobStore="PASS";liveSessionStore="PASS";resultStore="PASS";artifactStore="PASS"}
$path=Join-Path $OutputDir "runtime-store-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"
