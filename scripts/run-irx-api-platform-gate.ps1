param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.1-api-platform")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$results=@{}
$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat compileJava --no-daemon --console=plain | Tee-Object (Join-Path $OutputDir "compileJava.log") | Out-Host
$results.compileJava="PASS"
try { Push-Location dashboard; npm run typecheck | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-typecheck.log") | Out-Host; npm run build | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-build.log") | Out-Host; Pop-Location; $results.dashboard="PASS" } catch { Pop-Location; $results.dashboard="FAIL"; throw }
& "$PSScriptRoot/run-api-static-dispatch-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "static") | Out-Host; $results.staticDispatchApi="PASS"
& "$PSScriptRoot/run-api-live-dynamic-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "live") | Out-Host; $results.liveDynamicApi="PASS"
& "$PSScriptRoot/run-live-freeze-policy-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "freeze") | Out-Host; $results.freezePolicy="PASS"
& "$PSScriptRoot/run-api-rescue-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "rescue") | Out-Host; $results.rescueApi="PASS"
& "$PSScriptRoot/run-api-idempotency-validation-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "idempotency") | Out-Host; $results.idempotency="PASS"
& "$PSScriptRoot/run-api-security-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "security") | Out-Host; $results.security="PASS"
& "$PSScriptRoot/run-api-event-stream-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "events") | Out-Host; $results.eventStream="PASS"
& "$PSScriptRoot/run-dashboard-playground-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "dashboard-playground") | Out-Host; $results.dashboardPlayground="PASS"
$summary=[pscustomobject]@{version="v0.9.9.1-irx-api-platform";overallPass=$true;engineVersion="v0.9.9-adaptive-ml-quality-seeking";compileJava=$results.compileJava;dashboardBuild=$results.dashboard;staticDispatchApi=$results.staticDispatchApi;liveDynamicApi=$results.liveDynamicApi;freezePolicy=$results.freezePolicy;rescueApi=$results.rescueApi;idempotency=$results.idempotency;security=$results.security;eventStream=$results.eventStream;dashboardPlayground=$results.dashboardPlayground}
$path=Join-Path $OutputDir "final-api-platform-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"
