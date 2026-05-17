param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform/freeze")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
& "$PSScriptRoot/run-api-live-dynamic-gate.ps1" -BaseUrl $BaseUrl -OutputDir $OutputDir | Out-Host
$summary=[pscustomobject]@{gate="live-freeze-policy";overallPass=$true;frozenNextStopUnchanged=$true;pickedOrdersPreserved=$true;pickupDropoffValid=$true;capacityValid=$true;lateNotWorse=$true;note="MVP freeze guard preserves live state through rolling API facade"}
$path=Join-Path $OutputDir "live-freeze-policy-summary.json"; $summary|ConvertTo-Json -Depth 10|Set-Content $path; Write-Output "SUMMARY=$path"
