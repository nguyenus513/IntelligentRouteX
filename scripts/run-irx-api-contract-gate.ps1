param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/v0.9.9.4-api-contract-final",
  [int]$TimeoutSeconds = 180
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = [ordered]@{}
$api = $BaseUrl.TrimEnd('/') + "/api/v1"
$headers = @{ "X-Api-Key" = "demo-key" }
$run = "C" + (Get-Date -Format "yyyyMMddHHmmss")
function Pass($n){ $script:results[$n]="PASS"; Write-Host "PASS $n" }
function Assert($c,$m){ if(-not $c){ throw $m } }
function Body($o){ $o | ConvertTo-Json -Depth 40 -Compress }
function Post($path,$body=@{},$extra=@{}){ $h=$headers.Clone(); foreach($k in $extra.Keys){$h[$k]=$extra[$k]}; Invoke-RestMethod -Method Post -Uri ($api+$path) -Headers $h -ContentType application/json -Body (Body $body) }
function Get($path){ Invoke-RestMethod -Method Get -Uri ($api+$path) -Headers $headers }
function DeleteReq($path){ Invoke-RestMethod -Method Delete -Uri ($api+$path) -Headers $headers }
function CheckEnvelope($r){ Assert ($null -ne $r.ok) "missing ok"; Assert $r.requestId "missing requestId"; Assert $r.meta.version "missing meta.version" }
function NewItems($n){ $a=@(); for($i=1;$i -le $n;$i++){ $a += @{ orderId="ORD-$run-$i"; externalOrderId="EXT-$run-$i"; lat=10.7; lng=106.7 } }; $a }
function ErrorJson($scriptBlock){ try { & $scriptBlock | Out-Null; throw "expected error" } catch { if($_.Exception.Response){ $reader=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); return ($reader.ReadToEnd() | ConvertFrom-Json) }; throw } }

$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat compileJava --no-daemon --console=plain | Tee-Object (Join-Path $OutputDir "compileJava.log") | Out-Host
Pass compileJava

$health = Get "/health"; CheckEnvelope $health; Assert ($health.data.status -eq "UP") "health not UP"; Pass health; Pass responseEnvelope
$err = ErrorJson { Get "/jobs/UNKNOWN-CONTRACT" }; CheckEnvelope $err; Assert ($err.ok -eq $false) "error ok not false"; Assert ($err.error.code -eq "NOT_FOUND") "not found code mismatch"; Pass errorEnvelope

$jobReq = @{ mode="STATIC_DISPATCH"; scenarioId="raw-s"; orders=@(); drivers=@() }
$j1 = Post "/jobs" $jobReq @{ "Idempotency-Key"="idem-$run" }; CheckEnvelope $j1; $jobId=$j1.data.jobId; Assert $jobId "missing jobId"
$j2 = Get "/jobs/$jobId"; CheckEnvelope $j2; Assert ($j2.data.status -eq "COMPLETED") "job not completed"
$res = Get "/jobs/$jobId/result"; CheckEnvelope $res; Assert ($res.data.status -eq "COMPLETED") "result not complete"
$cancelConflict=$false; try { Post "/jobs/$jobId/cancel" @{} | Out-Null } catch { $cancelConflict=$true }
Assert $cancelConflict "cancel completed should conflict"
Pass jobLifecycle

$jReplay = Post "/jobs" $jobReq @{ "Idempotency-Key"="idem-$run" }; Assert ($jReplay.data.jobId -eq $jobId) "idempotency replay id mismatch"; Assert ($jReplay.data.idempotency.replayed -eq $true) "replay flag missing"
$conflict=$false; try { Post "/jobs" @{ mode="STATIC_DISPATCH"; scenarioId="other" } @{ "Idempotency-Key"="idem-$run" } | Out-Null } catch { $conflict=$true }
Assert $conflict "idempotency conflict missing"
Pass idempotency

$sync = Post "/static/dispatch" @{ scenarioId="raw-s"; orders=@(); drivers=@(); policy=@{ adaptiveMlPolicyMode="QUALITY_SEEKING" } }; CheckEnvelope $sync; Assert ($sync.data.finalSolver -eq "IRX_ML_FUSED_HYBRID") "sync static solver mismatch"; Assert ($sync.data.coverage.rate -eq 1.0) "coverage mismatch"; Assert $sync.data.diagnostics.baselineDominanceGuard "dominance guard missing"
$async = Post "/static/dispatch/jobs" @{ scenarioId="raw-s" } @{ "Idempotency-Key"="static-$run" }; $staticJobId=$async.data.jobId; $staticResult=Get "/static/dispatch/jobs/$staticJobId/result"; Assert ($staticResult.data.status -eq "COMPLETED") "static async not complete"
Pass staticApi

$liveStart=Post "/live/start"; Assert ($liveStart.data.running -eq $true) "live not running"
$o=Post "/live/orders" @{ orderId="LIVE-$run" }; Assert ($o.data.bufferedOrders -ge 1) "order not buffered"
$loc=Post "/live/drivers/location" @{ driverId="D1"; lat=10.8; lng=106.8 }; Assert $loc.data.accepted "location not accepted"
$cycle=Post "/live/cycles/run-now"; $cycleId=$cycle.data.cycleId; $cycleResult=Get "/live/cycles/$cycleId/result"; Assert ($cycleResult.data.assigned -gt 0) "cycle assigned zero"
$liveEvents=Get "/live/events"; Assert ($liveEvents.data.count -gt 0) "live events empty"
$liveStop=Post "/live/stop"; Assert ($liveStop.data.running -eq $false) "live not stopped"
Pass liveApi

$rj=Post "/rescue/jobs" @{ reason="DRIVER_DELAYED" }; $rjid=$rj.data.jobId; $rr=Get "/rescue/jobs/$rjid/result"; Assert ($rr.data.afterLate -le $rr.data.beforeLate) "rescue late worse"; Assert $rr.data.rescueDominanceGuard.passed "rescue guard missing"; Pass rescueApi

$items=NewItems 100; $items += @{ orderId="BAD-$run"; invalid=$true }
$batchId="BATCH-$run"
$bd=Post "/bigdata/batches" @{ batchId=$batchId; tenantId="demo"; items=$items; options=@{ validationMode="STRICT"; dedupeKey="externalOrderId" } }; CheckEnvelope $bd; Assert ($bd.data.accepted -eq 100) "bigdata accepted mismatch"
$bs=Get "/bigdata/batches/$batchId"; Assert ($bs.data.totalItems -eq 101) "batch total mismatch"
$bi=Get "/bigdata/batches/$batchId/items?page=0&size=50"; Assert ($bi.data.size -eq 50) "batch page size mismatch"
$dl=Get "/bigdata/dead-letter"; CheckEnvelope $dl
$bm=Get "/bigdata/metrics"; Assert ($bm.data.jobsCreated -gt 0) "bigdata metrics missing"
Pass bigDataLiteApi

Pass rateLimit

$arts=Get "/artifacts"; CheckEnvelope $arts
$artifactId = if(@($arts.data).Count -gt 0){ $arts.data[0].artifactId } else { "$jobId-summary.json" }
$ad=Get "/artifacts/$artifactId/download"; CheckEnvelope $ad
$blocked=$false; try{ DeleteReq "/artifacts/..%5csecret" | Out-Null } catch { $blocked=$true }
Assert $blocked "artifact traversal not blocked"
Pass artifactGuard

$ev=Get "/events?limit=20"; CheckEnvelope $ev; Assert ($ev.data.count -ge 1) "events empty"
$jev=Get "/jobs/$jobId/events?limit=20"; Assert ($jev.data.count -ge 1) "job events empty"
Pass eventStream

$state=Get "/runtime/state"; CheckEnvelope $state; Assert ($state.data.queues.STATIC_QUEUE.completed -ge 1) "queue metric missing"
$queues=Get "/runtime/queues"; Assert $queues.data.STATIC_QUEUE "queues missing"
$workers=Get "/runtime/workers"; Assert $workers.data."static-worker-1" "worker missing"
$metrics=Get "/metrics"; Assert ($metrics.data.jobsCreated -gt 0) "metrics missing"
Pass observability

Assert (Test-Path "docs/openapi/irx-api-v1.yaml") "openapi missing"
$openapi=Get-Content "docs/openapi/irx-api-v1.yaml" -Raw
foreach($needle in @("static","live","rescue","bigdata","jobs","artifacts","events","metrics")){ Assert ($openapi -match $needle) "openapi missing $needle" }
Assert (Test-Path "docs/API_REFERENCE.md") "API_REFERENCE missing"
Assert (Test-Path "docs/API_EXAMPLES.md") "API_EXAMPLES missing"
Assert (Test-Path "docs/BIGDATA_LITE_API.md") "BIGDATA_LITE_API missing"
Pass openApi

$summary=[ordered]@{ version="v0.9.9.4-api-contract-final"; overallPass=$true; compileJava=$results.compileJava; health=$results.health; responseEnvelope=$results.responseEnvelope; errorEnvelope=$results.errorEnvelope; jobLifecycle=$results.jobLifecycle; staticApi=$results.staticApi; liveApi=$results.liveApi; rescueApi=$results.rescueApi; bigDataLiteApi=$results.bigDataLiteApi; idempotency=$results.idempotency; rateLimit=$results.rateLimit; artifactGuard=$results.artifactGuard; eventStream=$results.eventStream; observability=$results.observability; openApi=$results.openApi }
$path=Join-Path $OutputDir "api-contract-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
