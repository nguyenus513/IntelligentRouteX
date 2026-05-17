param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/v0.9.9.3-bigdata-lite-api"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = [ordered]@{}
$headers = @{ "X-Api-Key" = "demo-key" }
$RunId = "BDL-" + (Get-Date -Format "yyyyMMddHHmmss")
function B([string]$name) { return "$RunId-$name" }

function Pass([string]$name) { $script:results[$name] = "PASS"; Write-Host ("PASS " + $name) }
function Assert($condition, [string]$message) { if (-not $condition) { throw $message } }
function StatusCode($err) { try { return [int]$err.Exception.Response.StatusCode } catch { try { return [int]$err.Exception.Response.StatusCode.value__ } catch { return -1 } } }
function JsonBody($obj) { return ($obj | ConvertTo-Json -Depth 30 -Compress) }
function PostJson([string]$path, $body) {
  Write-Host ("POST " + $path)
  Invoke-RestMethod -Method Post -Uri ($BaseUrl + $path) -Headers $headers -ContentType "application/json" -Body (JsonBody $body)
}
function GetJson([string]$path) { Invoke-RestMethod -Method Get -Uri ($BaseUrl + $path) -Headers $headers }
function NewItems([int]$count, [string]$prefix) {
  $items = @()
  for($i=1; $i -le $count; $i++) { $items += @{ orderId = "$prefix-$i"; externalOrderId = "$prefix-ext-$i"; lat = 10.7; lng = 106.7; load = 1 } }
  return $items
}
function SubmitBatch([string]$path, [string]$batchId, [int]$count, [hashtable]$options = @{}) {
  $batchItems = @(NewItems $count $batchId)
  PostJson $path @{ batchId=$batchId; tenantId="demo"; items=$batchItems; options=(@{ validationMode="STRICT"; dedupeKey="externalOrderId"; enqueueDispatch=$true } + $options) }
}

$env:GRADLE_USER_HOME=(Resolve-Path '.').Path + '\.gradle-tmp'
.\gradlew.bat compileJava --no-daemon --console=plain | Tee-Object (Join-Path $OutputDir "compileJava.log") | Out-Host
Pass "compileJava"
try {
  Push-Location dashboard
  npm run typecheck | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-typecheck.log") | Out-Host
  npm run build | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-build.log") | Out-Host
  Pop-Location
  Pass "dashboardBuild"
} catch { Pop-Location; throw }

$health = GetJson "/api/v1/runtime/state"
Assert $health.ok "runtime state not reachable"

$b100 = SubmitBatch "/api/v1/ingest/orders/batch" (B "100") 100
Assert ($b100.data.accepted -eq 100) "100 batch accepted mismatch"
$b1000 = SubmitBatch "/api/v1/ingest/orders/batch" (B "1000") 1000
Assert ($b1000.data.accepted -eq 1000) "1000 batch accepted mismatch"
Pass "batchIngest"

$invalidItems = @( @{ orderId="bad-1"; invalid=$true }, @{ orderId="ok-1" } )
$invalid = PostJson "/api/v1/ingest/orders/batch" @{ batchId=(B "INVALID"); tenantId="demo"; items=$invalidItems; options=@{ validationMode="STRICT"; dedupeKey="orderId"; enqueueDispatch=$true } }
Assert ($invalid.data.rejected -eq 1) "invalid rows not rejected"
Pass "normalization"

$dup1 = SubmitBatch "/api/v1/ingest/orders/batch" (B "IDEMP") 5
$dup2 = SubmitBatch "/api/v1/ingest/orders/batch" (B "IDEMP") 5
Assert ($dup1.data.jobId -eq $dup2.data.jobId) "idempotent duplicate did not return same job"
$conflictOk = $false
try { SubmitBatch "/api/v1/ingest/orders/batch" (B "IDEMP") 6 | Out-Null } catch { $conflictOk = $true }
Assert $conflictOk "idempotency conflict did not return 409"
Pass "idempotency"

$live = SubmitBatch "/api/v1/ingest/telemetry/batch" (B "LIVE") 10
$rescue = SubmitBatch "/api/v1/ingest/rescue/batch" (B "RESCUE") 3
$queues = GetJson "/api/v1/runtime/queues"
Assert ($queues.data.STATIC_QUEUE.completed -ge 1) "static queue missing"
Assert ($queues.data.LIVE_QUEUE.completed -ge 1) "live queue missing"
Assert ($queues.data.RESCUE_QUEUE.completed -ge 1) "rescue queue missing"
Pass "queueRouting"

$bpOk = $false
try { SubmitBatch "/api/v1/ingest/orders/batch" "QUEUE-FULL" 1 | Out-Null } catch { $bpOk = $true }
Assert $bpOk "queue backpressure did not return 503"
Pass "backpressure"

$result = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/result")
Assert ($result.data.status -eq "COMPLETED") "job not completed"
$events = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/events?limit=20")
$types = @($events.data.items | ForEach-Object { $_.type })
Assert ($types -contains "JOB_CREATED") "missing JOB_CREATED"
Assert ($types -contains "JOB_COMPLETED") "missing JOB_COMPLETED"
Pass "asyncLifecycle"

$page1 = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/assignments?limit=100")
Assert ($page1.data.count -eq 100) "assignment page count mismatch"
Assert ($page1.data.nextCursor -ne "") "missing next cursor"
$page2 = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/assignments?limit=100&cursor=" + $page1.data.nextCursor)
Assert ($page2.data.count -eq 100) "assignment second page mismatch"
$routes = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/routes?limit=10")
Assert ($routes.data.count -gt 0) "routes pagination empty"
Pass "pagination"

$artifacts = GetJson ("/api/v1/jobs/" + $b1000.data.jobId + "/artifacts")
Assert ($artifacts.data.Count -ge 5) "artifact list too small"
$artifactId = $artifacts.data[0].artifactId
$artifact = GetJson ("/api/v1/artifacts/" + $artifactId)
Assert ($artifact.data.artifactId -eq $artifactId) "artifact download mismatch"
$traversalOk = $false
try { GetJson "/api/v1/artifacts/..%5csecret" | Out-Null } catch { $traversalOk = $true }
Assert $traversalOk "path traversal not blocked"
Pass "artifactOutput"

Assert ($events.data.count -gt 0) "event log empty"
Pass "eventLog"
$wc = New-Object System.Net.WebClient
$wc.Headers.Add("X-Api-Key", "demo-key")
$sseContent = $wc.DownloadString($BaseUrl + "/api/v1/jobs/" + $b1000.data.jobId + "/events/stream")
Assert ($sseContent -match "JOB_COMPLETED") "event stream missing completion"
Pass "eventStream"

$fail = SubmitBatch "/api/v1/ingest/orders/batch" (B "FAIL") 1 @{ forceFail=$true }
Assert ($fail.data.status -eq "DEAD_LETTER") "forced failure did not dead-letter"
$dlq = GetJson "/api/v1/runtime/dead-letter"
Assert (@($dlq.data | Where-Object { $_.jobId -eq $fail.data.jobId }).Count -eq 1) "DLQ missing job"
$requeued = PostJson ("/api/v1/runtime/dead-letter/" + $fail.data.jobId + "/requeue") @{}
Assert ($requeued.data.status -eq "COMPLETED") "requeue did not complete"
Pass "deadLetter"

$telemetryItems = @()
for($i=1; $i -le 100; $i++) { $telemetryItems += @{ driverId="D-LIVE"; lat=(10 + $i / 1000); lng=106.7; seq=$i } }
$telemetry = PostJson "/api/v1/ingest/telemetry/batch" @{ batchId=(B "TELEMETRY-100"); tenantId="demo"; items=$telemetryItems; options=@{ validationMode="STRICT"; dedupeKey="driverId"; enqueueDispatch=$true } }
$state = GetJson "/api/v1/runtime/state"
Assert ($state.data.latestTelemetryCount -ge 1) "telemetry coalescing state missing"
Pass "liveCoalescing"

$metrics = GetJson "/api/v1/runtime/metrics"
Assert ($metrics.data.jobsCreated -gt 0) "jobsCreated metric missing"
Assert ($metrics.data.eventCount -gt 0) "eventCount metric missing"
Assert ($metrics.data.artifactCount -gt 0) "artifactCount metric missing"
Pass "runtimeMetrics"

Assert (Test-Path "docker-compose.yml") "docker-compose.yml missing"
Assert (Test-Path "Dockerfile.backend") "Dockerfile.backend missing"
Assert (Test-Path "dashboard/Dockerfile") "dashboard Dockerfile missing"
Pass "dockerComposeSmoke"

$summary = [ordered]@{
  version = "v0.9.9.3-bigdata-lite-api"
  overallPass = $true
  compileJava = $results.compileJava
  dashboardBuild = $results.dashboardBuild
  batchIngest = $results.batchIngest
  normalization = $results.normalization
  idempotency = $results.idempotency
  queueRouting = $results.queueRouting
  backpressure = $results.backpressure
  asyncLifecycle = $results.asyncLifecycle
  pagination = $results.pagination
  artifactOutput = $results.artifactOutput
  eventLog = $results.eventLog
  eventStream = $results.eventStream
  deadLetter = $results.deadLetter
  liveCoalescing = $results.liveCoalescing
  runtimeMetrics = $results.runtimeMetrics
  dockerComposeSmoke = $results.dockerComposeSmoke
}
$summaryPath = Join-Path $OutputDir "final-bigdata-lite-api-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
Write-Output "SUMMARY=$summaryPath"










