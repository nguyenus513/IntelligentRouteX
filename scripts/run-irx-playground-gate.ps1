param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$DashboardUrl = "http://localhost:5173",
  [string]$OutputDir = "artifacts/test-reports/v0.9.9.5-irx-playground",
  [int]$TimeoutSeconds = 240
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$api = $BaseUrl.TrimEnd('/') + "/api/v1"
$headers = @{ "X-Api-Key" = "demo-key" }
$results = [ordered]@{}
$run = "PG" + (Get-Date -Format "yyyyMMddHHmmss")
function Pass($name){ $script:results[$name] = "PASS"; Write-Host "PASS $name" }
function Assert($condition, $message){ if(-not $condition){ throw $message } }
function Body($obj){ $obj | ConvertTo-Json -Depth 40 -Compress }
function Post($path, $body=@{}, $extra=@{}){ $h=$headers.Clone(); foreach($key in $extra.Keys){ $h[$key]=$extra[$key] }; Invoke-RestMethod -Method Post -Uri ($api+$path) -Headers $h -ContentType application/json -Body (Body $body) }
function Get($path){ Invoke-RestMethod -Uri ($api+$path) -Headers $headers }
function Items($n){ $a=@(); for($i=1; $i -le $n; $i++){ $a += @{ orderId="ORD-$run-$i"; externalOrderId="EXT-$run-$i"; lat=10.7; lng=106.7 } }; $a }

Push-Location dashboard
npm run typecheck | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-typecheck.log") | Out-Host
Pass dashboardTypecheck
npm run build | Tee-Object (Join-Path (Resolve-Path "..\$OutputDir") "dashboard-build.log") | Out-Host
Pass dashboardBuild
Pop-Location

$health = Get "/health"
Assert ($health.ok -eq $true) "backend health envelope failed"
Assert ($health.data.status -eq "UP") "backend not UP"
Pass backendHealth

$main = Get-Content dashboard/src/main.tsx -Raw
Assert ($main -match "'/playground'") "/playground route missing"
Assert (Test-Path dashboard/src/playground/IrxPlaygroundPage.tsx) "IrxPlaygroundPage missing"
Assert (Test-Path dashboard/src/playground/playgroundApi.ts) "playgroundApi missing"
Pass playgroundRouteExists

$static = Post "/static/dispatch/jobs" @{ scenarioId="raw-s"; orders=@(); drivers=@(); policy=@{ adaptiveMlPolicyMode="QUALITY_SEEKING" } } @{ "Idempotency-Key"="pg-static-$run" }
Assert $static.data.jobId "static job missing"
$staticJob = Get ("/jobs/" + $static.data.jobId)
Assert ($staticJob.data.status -eq "COMPLETED") "static job not completed"
$staticResult = Get ("/jobs/" + $static.data.jobId + "/result")
Assert ($staticResult.data.status -eq "COMPLETED") "static result not completed"
Pass staticFlow

Post "/live/start" @{} | Out-Null
Post "/live/orders" @{ orderId="LIVE-$run"; pickup=@{lat=10.7;lng=106.7}; dropoff=@{lat=10.8;lng=106.8} } | Out-Null
Post "/live/drivers/location" @{ driverId="D-LIVE"; lat=10.75; lng=106.75 } | Out-Null
$cycle = Post "/live/cycles/run-now" @{}
Assert $cycle.data.cycleId "cycle missing"
$cycleResult = Get ("/live/cycles/" + $cycle.data.cycleId + "/result")
Assert ($cycleResult.data.assigned -gt 0) "cycle assigned zero"
$liveEvents = Get "/live/events"
Assert ($liveEvents.data.count -gt 0) "live events missing"
Pass liveFlow

$rescue = Post "/rescue/jobs" @{ reason="DRIVER_DELAYED" }
Assert $rescue.data.jobId "rescue job missing"
$rescueResult = Get ("/rescue/jobs/" + $rescue.data.jobId + "/result")
Assert ($rescueResult.data.lateNotWorse -eq $true) "rescue late guard failed"
Assert ($rescueResult.data.rescueDominanceGuard.passed -eq $true) "rescue guard missing"
Pass rescueFlow

$batchId = "BATCH-$run"
$batchItems = Items 120
$batchItems += @{ orderId="BAD-$run"; externalOrderId="BAD-$run"; invalid=$true; lat=0; lng=0 }
$batch = Post "/bigdata/batches" @{ batchId=$batchId; tenantId="demo"; items=$batchItems; options=@{ validationMode="STRICT"; dedupeKey="externalOrderId" } } @{ "Idempotency-Key"="pg-batch-$run" }
Assert ($batch.data.accepted -eq 120) "batch accepted mismatch"
$batchStatus = Get ("/bigdata/batches/" + $batchId)
Assert ($batchStatus.data.totalItems -eq 121) "batch total mismatch"
$batchPage = Get ("/bigdata/batches/" + $batchId + "/items?page=0&size=50")
Assert ($batchPage.data.size -eq 50) "batch pagination missing"
Pass bigDataFlow

$events = Get ("/jobs/" + $static.data.jobId + "/events?limit=20")
Assert ($events.data.count -gt 0) "job events missing"
Pass events

$artifacts = Get ("/jobs/" + $static.data.jobId + "/artifacts")
Assert (@($artifacts.data).Count -gt 0) "artifacts missing"
$artifactId = $artifacts.data[0].artifactId
$artifact = Get ("/artifacts/" + $artifactId)
Assert ($artifact.data.artifactId -eq $artifactId) "artifact fetch mismatch"
Pass artifacts

$source = Get-Content dashboard/src/playground/IrxPlaygroundPage.tsx -Raw
foreach($needle in @('AdaptiveMlPanel','BaselinePanel','ResultPanel','EventArtifactPanel','RawJsonPanel','AssignmentTable')){ Assert ($source -match $needle) "missing panel $needle" }

$summary = [ordered]@{
  version = "v0.9.9.5-irx-playground"
  overallPass = $true
  dashboardTypecheck = $results.dashboardTypecheck
  dashboardBuild = $results.dashboardBuild
  backendHealth = $results.backendHealth
  playgroundRouteExists = $true
  staticFlow = $results.staticFlow
  liveFlow = $results.liveFlow
  rescueFlow = $results.rescueFlow
  bigDataFlow = $results.bigDataFlow
  events = $results.events
  artifacts = $results.artifacts
  adaptiveMlPanel = "PASS"
  baselinePanel = "PASS"
  resultSummary = "PASS"
  rawJson = "PASS"
  dashboardUrl = $DashboardUrl
}
$path = Join-Path $OutputDir "playground-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
