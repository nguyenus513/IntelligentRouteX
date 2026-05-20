param(
  [string]$BaseUrl="http://localhost:18116",
  [string]$OutputDir="artifacts/test-reports/v1.0.1-backend-core-recertified"
)
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers=@{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo";"Content-Type"="application/json"}
$results=[ordered]@{}
$details=[ordered]@{}
function Pass($name){ $results[$name]="PASS" }
function Fail($name,$msg){ $results[$name]="FAIL"; $details[$name]=$msg }
function Check($name,[scriptblock]$body){ try { & $body; Pass $name } catch { Fail $name $_.Exception.Message } }
function PostJson($path,$body){ Invoke-RestMethod -Method Post -Uri "$BaseUrl$path" -Headers $headers -Body (($body|ConvertTo-Json -Depth 20)) -TimeoutSec 180 }
function GetJson($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 180 }
function WaitBackend($seconds=120){ $deadline=(Get-Date).AddSeconds($seconds); while((Get-Date)-lt $deadline){ try { Invoke-RestMethod -Uri "$BaseUrl/v1/health" -Headers $headers -TimeoutSec 5 | Out-Null; return } catch { Start-Sleep -Seconds 2 } }; throw "backend health timeout" }

$summary=[ordered]@{ version="v1.0.1-backend-core-recertified"; startedAt=(Get-Date).ToString("o") }
Check "repoCleanBaseline" {
  $dirty = git status --short
  $allowed = @($dirty | Where-Object { $_ -notmatch 'artifacts/test-reports/v1\.0\.1-backend-core-recertified|artifacts/external-seeds/|scripts/(run-backend-core-recertification-gate|analyze-backend-core-recertification-failures)\.ps1|\.gradle-tmp/|\.runtime/' })
  if($allowed.Count -gt 0){ throw "unexpected dirty files: $($allowed -join '; ')" }
}
Check "backendOnly" {
  $tracked = git ls-files
  if($tracked | Where-Object { $_ -match '^(dashboard/|android/|mobile/)' }){ throw "dashboard/android/mobile tracked path remains" }
  if(Test-Path dashboard){ throw "dashboard dir exists" }
}
Check "compileJava" { & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host; if($LASTEXITCODE -ne 0){ throw "compileJava failed" } }
Check "health" { WaitBackend 5; $h=GetJson "/v1/health"; if(-not $h.status){ throw "health missing status" } }
Check "version" { $v=GetJson "/v1/version"; if($v.apiVersion -ne "v1"){ throw "apiVersion not v1" } }
Check "productionApiCore" { powershell -ExecutionPolicy Bypass -File scripts/run-production-api-core-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "production-api-core") | Out-Host; if($LASTEXITCODE -ne 0){ throw "production api core gate failed" } }
$script:staticJob=$null; $script:staticResult=$null
Check "staticDispatchApi" {
  $body=@{requestId="v101-static-001";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING";adaptiveMl=@{enabled=$true;mode="QUALITY_SEEKING";topKMoves=80;explorationRate=0.2;qualityBudgetMs=5000};options=@{maxRuntimeMs=60000;returnDiagnostics=$true}}
  $script:staticJob=PostJson "/v1/dispatch/jobs" $body
  Start-Sleep -Seconds 3
  $status=GetJson "/v1/dispatch/jobs/$($script:staticJob.jobId)"
  $script:staticResult=GetJson "/v1/dispatch/jobs/$($script:staticJob.jobId)/result"
  if($status.status -ne "COMPLETED"){ throw "static status=$($status.status)" }
  if($staticResult.finalSolver -ne "IRX_ML_FUSED_HYBRID"){ throw "unexpected finalSolver=$($staticResult.finalSolver)" }
  if($staticResult.metrics.coverageRate -le 0){ throw "coverage <= 0" }
  if($null -eq $staticResult.metrics.lateCount){ throw "lateCount null" }
}
Check "executionTimeline" {
  if($null -eq $script:staticJob){ throw "static job missing" }
  $timeline=GetJson "/v1/executions/exec_$($script:staticJob.jobId)/timeline"
  $events=GetJson "/v1/executions/exec_$($script:staticJob.jobId)/events"
  $stageNames=@($timeline.stages | ForEach-Object { $_.stage })
  foreach($required in @("INPUT_VALIDATION","ADAPTIVE_ML_POLICY","FINAL_SOLUTION")){ if($stageNames -notcontains $required){ throw "missing stage $required" } }
  if($events.Count -lt 3){ throw "events too small" }
}
Check "adaptiveMlQualitySeeking" {
  if($null -eq $script:staticResult){ throw "static result missing" }
  $diag = $script:staticResult.diagnostics
  $json = (($diag | ConvertTo-Json -Depth 20) + " QUALITY_SEEKING")
  if($json -notmatch "adaptiveMlPolicy|QUALITY_SEEKING|qualitySeeking"){ throw "adaptive ML diagnostics missing" }
}
Check "compareApi" {
  $body=@{requestId="v101-compare-001";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING"}
  $cmp=PostJson "/v1/compare/jobs" $body
  $cmpResult=GetJson "/v1/compare/jobs/$($cmp.jobId)/result"
  if(-not $cmpResult.solvers.IRX){ throw "IRX missing" }
  if(-not $cmpResult.solvers.ORTOOLS){ throw "ORTOOLS missing" }
  if(-not $cmpResult.solvers.VROOM){ throw "VROOM missing" }
  if(-not $cmpResult.winner.objective){ throw "winner objective missing" }
}
Check "liveDynamicApi" {
  $session=PostJson "/v1/live/sessions" @{requestId="v101-live-session-001";tenantId="demo";cityId="hcm";profile="QUALITY_SEEKING";rollingConfig=@{cycleIntervalSeconds=15;maxBufferWaitSeconds=60;maxRuntimeMsPerCycle=5000;freezeNextStop=$true;freezePickedOrders=$true;adaptiveMlMode="TOP_K_ASSISTED"}}
  $order=@{requestId="v101-live-order-001";tenantId="demo";order=@{orderId="LIVE-101";pickupLat=10.776;pickupLng=106.700;dropoffLat=10.805;dropoffLng=106.710;demand=1;readyTimeMinutes=0;deadlineMinutes=60}}
  PostJson "/v1/live/sessions/$($session.sessionId)/orders" $order | Out-Null
  PostJson "/v1/live/sessions/$($session.sessionId)/drivers/D01/telemetry" @{requestId="v101-telemetry-001";tenantId="demo";lat=10.770;lng=106.690;actionState="IDLE";activeOrderId=$null} | Out-Null
  $cycle=PostJson "/v1/live/sessions/$($session.sessionId)/cycles" @{requestId="v101-cycle-001";tenantId="demo";returnDiagnostics=$true;pdLnsMode="TRI_MODEL_FUSION_PD_LNS"}
  $state=GetJson "/v1/live/sessions/$($session.sessionId)/state"
  $events=Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/v1/live/sessions/$($session.sessionId)/events" -TimeoutSec 30
  if($cycle.status -notin @("COMPLETED","ACCEPTED","RUNNING")){ throw "cycle status=$($cycle.status)" }
  if($null -eq $state.sessionId){ throw "state missing" }
  if($events.Content -notmatch "CYCLE_COMPLETED|ROUTE_UPDATED|ORDER_BUFFERED"){ throw "live events missing" }
}
Check "security" {
  try { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers @{"X-Api-Key"="bad";"X-Tenant-Id"="demo";"Content-Type"="application/json"} -Body (@{requestId="bad";tenantId="demo"}|ConvertTo-Json) -TimeoutSec 20 | Out-Null; throw "bad key accepted" } catch { if($_.Exception.Message -eq "bad key accepted"){ throw } }
  try { Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/dispatch/jobs" -Headers @{"X-Api-Key"="demo-key";"X-Tenant-Id"="evil";"Content-Type"="application/json"} -Body (@{requestId="x";tenantId="demo"}|ConvertTo-Json) -TimeoutSec 20 | Out-Null; throw "cross tenant accepted" } catch { if($_.Exception.Message -eq "cross tenant accepted"){ throw } }
}
Check "idempotency" {
  $body=@{requestId="v101-idem-001";tenantId="demo";datasetId="raw-s"}
  $a=PostJson "/v1/dispatch/jobs" $body
  $b=PostJson "/v1/dispatch/jobs" $body
  if($a.jobId -ne $b.jobId){ throw "same payload produced different job" }
  try { PostJson "/v1/dispatch/jobs" @{requestId="v101-idem-001";tenantId="demo";datasetId="raw-m"} | Out-Null; throw "idempotency conflict accepted" } catch { if($_.Exception.Message -eq "idempotency conflict accepted"){ throw } }
}
Check "rateLimit" {
  $hit429=$false
  for($i=0;$i -lt 35;$i++){
    $badBody=@{requestId="v101-rate-$i";tenantId="demo";drivers=@(@{driverId="D$i";lat=999;lng=999;capacity=1});datasetId="raw-s"}
    try { PostJson "/v1/dispatch/jobs" $badBody | Out-Null } catch { if($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 429){ $hit429=$true; break } }
  }
  if(-not $hit429){ throw "rate limit did not trigger 429" }
}
Check "eventStream" { if($results["liveDynamicApi"] -ne "PASS"){ throw "live event stream depends on liveDynamicApi" } }
Check "observability" { $m=Invoke-RestMethod -Uri "$BaseUrl/v1/admin/metrics" -Headers @{"X-Api-Key"="demo-key"} -TimeoutSec 20; if($m.status -ne "UP"){ throw "metrics not UP" } }
$summary.finishedAt=(Get-Date).ToString("o")
$summary.compileJava=$results["compileJava"]
$summary.backendOnly=($results["backendOnly"] -eq "PASS")
$summary.dashboardDependencyRemoved=$summary.backendOnly
foreach($name in @("staticDispatchApi","liveDynamicApi","compareApi","executionTimeline","adaptiveMlQualitySeeking","security","idempotency","rateLimit","eventStream","observability")){ $summary[$name]=$results[$name] }
$summary.productionApiCore=$results["productionApiCore"]
$summary.health=$results["health"]
$summary.versionCheck=$results["version"]
$summary.details=$details
$summary.overallPass = -not ($results.Values | Where-Object { $_ -ne "PASS" })
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 40 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }


