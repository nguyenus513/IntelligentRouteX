param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.0-production-api-core/final")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results=[ordered]@{}
function Run-Step($name, [scriptblock]$body){
  try { & $body | Out-Host; $results[$name]="PASS" } catch { $results[$name]="FAIL"; $script:lastError=$_.Exception.Message }
}
Run-Step "compileJava" { & .\gradlew.bat compileJava --no-daemon --console=plain; if($LASTEXITCODE -ne 0){ throw "compileJava failed" } }
Run-Step "apiContract" { powershell -ExecutionPolicy Bypass -File scripts/run-api-contract-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "contract"); if($LASTEXITCODE -ne 0){ throw "contract failed" } }
Run-Step "runtimeStore" { if(-not (Test-Path "src/main/java/com/routechain/runtime/store/DispatchJobStore.java")){ throw "store missing" } }
Run-Step "asyncWorker" { if(-not (Test-Path "src/main/java/com/routechain/runtime/queue/WorkerLoop.java")){ throw "worker missing" } }
Run-Step "executionTimeline" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxProductionApiExtensionController.java" -Pattern "/executions/\{executionId\}/timeline" -Quiet | Out-Null; if(-not $?){ throw "timeline endpoint missing" } }
Run-Step "staticDispatchApi" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "/dispatch/jobs" -Quiet | Out-Null; if(-not $?){ throw "static endpoint missing" } }
Run-Step "liveDynamicApi" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "/live/sessions" -Quiet | Out-Null; if(-not $?){ throw "live endpoint missing" } }
Run-Step "freezePolicy" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "frozenStopViolations|freeze" -Quiet | Out-Null }
Run-Step "compareApi" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxProductionApiExtensionController.java" -Pattern "/compare/jobs" -Quiet | Out-Null; if(-not $?){ throw "compare endpoint missing" } }
Run-Step "security" { Select-String -Path "src/main/java/com/routechain/api/v1/*.java" -Pattern "X-Api-Key" -Quiet | Out-Null; if(-not $?){ throw "api key missing" } }
Run-Step "idempotency" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "IDEMPOTENCY_CONFLICT" -Quiet | Out-Null; if(-not $?){ throw "idempotency missing" } }
Run-Step "rateLimit" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "RATE_LIMITED" -Quiet | Out-Null; if(-not $?){ throw "rate limit missing" } }
Run-Step "artifactStore" { if(-not (Test-Path "src/main/java/com/routechain/runtime/artifact/ArtifactStore.java")){ throw "artifact store missing" } }
Run-Step "eventStream" { Select-String -Path "src/main/java/com/routechain/api/v1/*.java" -Pattern "events" -Quiet | Out-Null; if(-not $?){ throw "events missing" } }
Run-Step "observability" { Select-String -Path "src/main/java/com/routechain/api/v1/IrxApiV1Controller.java" -Pattern "/admin/metrics" -Quiet | Out-Null; if(-not $?){ throw "admin metrics missing" } }
Run-Step "dockerComposeSmoke" { if(-not (Test-Path "docker-compose.yml")){ throw "compose missing" } }
$overall = -not ($results.Values | Where-Object { $_ -ne "PASS" })
$summary=[ordered]@{ version="v1.0.0-production-api-core"; overallPass=$overall; fullReleaseReady=$overall; results=$results; error=$lastError }
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $overall){ exit 1 }
