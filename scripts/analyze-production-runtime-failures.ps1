param([string]$EvidenceDir="artifacts/test-reports/v0.9.9.2-production-runtime", [string]$Output="artifacts/test-reports/v0.9.9.2-production-runtime/production-runtime-failure-analysis.json")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent)|Out-Null
$failureType="NONE"; $recommendation="all production runtime gates pass or no failed gate summary found"
$failed=Get-ChildItem $EvidenceDir -Recurse -Filter "*-summary.json" -ErrorAction SilentlyContinue | ForEach-Object { $j=Get-Content $_.FullName -Raw|ConvertFrom-Json; if($j.overallPass -eq $false){[pscustomobject]@{path=$_.FullName;gate=$j.gate}} }
if($failed){ $gate=$failed[0].gate; $failureType=switch -Regex ($gate){ "store" {"STORE_FAILURE";break} "queue" {"QUEUE_ROUTING_FAILURE";break} "worker" {"WORKER_TIMEOUT";break} "security" {"SECURITY_BYPASS";break} "rate" {"RATE_LIMIT_BUG";break} "artifact" {"ARTIFACT_ACCESS_BUG";break} "event" {"EVENT_STREAM_FAILURE";break} "dashboard" {"DASHBOARD_API_BINDING_FAILURE";break} "docker" {"DOCKER_RUNTIME_FAILURE";break} default {"API_CONTRACT_FAILURE"} }; $recommendation="fix failed gate $gate then rerun slice and final gate" }
[pscustomobject]@{failureType=$failureType;recommendation=$recommendation;failed=$failed}|ConvertTo-Json -Depth 10|Set-Content $Output
Write-Output "SUMMARY=$Output"; if($failureType -ne "NONE"){exit 1}
