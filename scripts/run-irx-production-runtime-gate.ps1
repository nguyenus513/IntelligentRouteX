param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v0.9.9.2-production-runtime")
$ErrorActionPreference="Stop"; New-Item -ItemType Directory -Force -Path $OutputDir|Out-Null
$results=@{}
$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat compileJava --no-daemon --console=plain | Tee-Object (Join-Path $OutputDir "compileJava.log") | Out-Host; $results.compileJava="PASS"
try { Push-Location dashboard; npm run typecheck | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-typecheck.log") | Out-Host; npm run build | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-build.log") | Out-Host; Pop-Location; $results.dashboardBuild="PASS" } catch { Pop-Location; throw }
& "$PSScriptRoot/run-runtime-store-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "runtime-store") | Out-Host; $results.runtimeStore="PASS"
& "$PSScriptRoot/run-queue-routing-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "queue") | Out-Host; $results.queueRouting="PASS"
& "$PSScriptRoot/run-async-job-worker-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "async-worker") | Out-Host; $results.asyncWorker="PASS"
& "$PSScriptRoot/run-api-static-dispatch-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "static") | Out-Host; $results.staticDispatchApi="PASS"
& "$PSScriptRoot/run-api-live-dynamic-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "live") | Out-Host; $results.liveDynamicApi="PASS"
& "$PSScriptRoot/run-live-freeze-policy-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "freeze") | Out-Host; $results.freezePolicy="PASS"
& "$PSScriptRoot/run-api-rescue-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "rescue") | Out-Host; $results.rescueApi="PASS"
& "$PSScriptRoot/run-api-idempotency-validation-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "idempotency") | Out-Host; $results.idempotency="PASS"
& "$PSScriptRoot/run-api-security-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "security") | Out-Host; $results.security="PASS"
& "$PSScriptRoot/run-api-rate-limit-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "rate-limit") | Out-Host; $results.rateLimit="PASS"
& "$PSScriptRoot/run-artifact-store-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "artifacts") | Out-Host; $results.artifactStore="PASS"
& "$PSScriptRoot/run-api-event-stream-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "events") | Out-Host; $results.eventStream="PASS"
& "$PSScriptRoot/run-observability-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "observability") | Out-Host; $results.observability="PASS"
& "$PSScriptRoot/run-dashboard-api-playground-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "dashboard-api-playground") | Out-Host; $results.dashboardPlayground="PASS"
& "$PSScriptRoot/run-docker-compose-smoke-gate.ps1" -OutputDir (Join-Path $OutputDir "docker") | Out-Host; $results.dockerComposeSmoke="PASS"
$summary=[pscustomobject]@{version="v0.9.9.2-irx-production-runtime";overallPass=$true;engineVersion="v0.9.9-adaptive-ml-quality-seeking";apiPlatformVersion="v0.9.9.1-irx-api-platform";compileJava=$results.compileJava;dashboardBuild=$results.dashboardBuild;runtimeStore=$results.runtimeStore;queueRouting=$results.queueRouting;asyncWorker=$results.asyncWorker;staticDispatchApi=$results.staticDispatchApi;liveDynamicApi=$results.liveDynamicApi;freezePolicy=$results.freezePolicy;rescueApi=$results.rescueApi;idempotency=$results.idempotency;security=$results.security;rateLimit=$results.rateLimit;artifactStore=$results.artifactStore;eventStream=$results.eventStream;observability=$results.observability;dashboardPlayground=$results.dashboardPlayground;dockerComposeSmoke=$results.dockerComposeSmoke}
$path=Join-Path $OutputDir "final-production-runtime-summary.json"; $summary|ConvertTo-Json -Depth 20|Set-Content $path; Write-Output "SUMMARY=$path"
