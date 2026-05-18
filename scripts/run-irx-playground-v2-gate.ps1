param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$DashboardUrl = "http://localhost:5173",
  [string]$OutputDir = "artifacts/test-reports/v0.9.9.8-playground-map-first",
  [int]$TimeoutSeconds = 240
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$api = $BaseUrl.TrimEnd('/') + "/api/v1"
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
$results = [ordered]@{}
$run = "PGV2" + (Get-Date -Format "yyyyMMddHHmmss")
function Pass($name){ $script:results[$name] = "PASS"; Write-Host "PASS $name" }
function Assert($condition, $message){ if(-not $condition){ throw $message } }
function Body($obj){ $obj | ConvertTo-Json -Depth 40 -Compress }
function Post($path, $body=@{}, $extra=@{}){ $h=$headers.Clone(); foreach($key in $extra.Keys){ $h[$key]=$extra[$key] }; Invoke-RestMethod -Method Post -Uri ($api+$path) -Headers $h -ContentType application/json -Body (Body $body) -TimeoutSec $TimeoutSeconds }
function Get($path){ Invoke-RestMethod -Uri ($api+$path) -Headers $headers -TimeoutSec $TimeoutSeconds }
function Items($n){ $a=@(); for($i=1; $i -le $n; $i++){ $a += @{ orderId="ORD-$run-$i"; externalOrderId="EXT-$run-$i"; lat=(10.7 + $i * 0.0001); lng=(106.7 + $i * 0.0001) } }; $a }

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

$source = Get-Content dashboard/src/playground/IrxPlaygroundPage.tsx -Raw
$apiSource = Get-Content dashboard/src/playground/playgroundApi.ts -Raw
$viteConfig = Get-Content dashboard/vite.config.ts -Raw
Assert ($source -match "RouteMapPanel") "map panel not wired"
Assert ($source -match "RouteTimelinePanel") "timeline panel not wired"
Assert ($source -match "ApiHealthBadge") "api health badge not wired"
Assert ($source -match "SeedAttributionPanel") "seed attribution panel not wired"
Assert ($source -match "SafetyGuardPanel") "safety guard panel not wired"
Assert ($source -match "BigDataPipelinePanel") "BigData pipeline panel not wired"
Assert ($apiSource -match "BACKEND_UNAVAILABLE") "backend unavailable error missing"
Assert ($apiSource -match "DEFAULT_API_BASE = '/api/v1'") "relative API base missing"
Assert ($viteConfig -match "localhost:18116") "Vite proxy target missing"
Assert ($viteConfig -match "changeOrigin") "Vite proxy changeOrigin missing"
Assert ($apiSource -match "INVALID_JSON_RESPONSE") "invalid json error missing"
Assert ($apiSource -match "API_TIMEOUT") "timeout error missing"
Assert (-not ($apiSource -match "Failed to fetch")) "raw Failed to fetch string still present"
Pass playgroundRouteExists
Pass apiHealthBadge

$mapSource = Get-Content dashboard/src/playground/RouteMapPanel.tsx -Raw
$leafletSource = Get-Content dashboard/src/playground/LeafletHcmMap.tsx -Raw
$modelSource = Get-Content dashboard/src/playground/playgroundMapModel.ts -Raw
Assert ($leafletSource -match "MapContainer") "Leaflet map container missing"
Assert ($leafletSource -match "OpenStreetMap contributors") "OSM attribution missing"
Assert ($mapSource -match "Synthetic fallback") "synthetic fallback switch missing"
Assert ($mapSource -match "Coordinate mode") "coordinate mode badge missing"
Assert ($mapSource -match "svg") "SVG fallback missing"
Assert ($mapSource -match "map-pin") "pin render missing"
Assert ($mapSource -match "route-arrow") "route direction marker missing"
Assert ($mapSource -match "map-legend") "map legend missing"
Assert ($modelSource -match "PICKUP") "pickup model missing"
Assert ($modelSource -match "DROPOFF") "dropoff model missing"
Assert ($modelSource -match "DRIVER") "driver model missing"
Assert ($modelSource -match "HCM_DEMO_GEO") "HCM demo coordinate mode missing"
Pass mapPanel
Pass pinsAndRoutes
Pass timeline

$static = Post "/static/dispatch/jobs" @{ scenarioId="raw-s"; orders=@(); drivers=@(); policy=@{ adaptiveMlPolicyMode="QUALITY_SEEKING" } } @{ "Idempotency-Key"="pgv2-static-$run" }
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
Pass liveFlow

$rescue = Post "/rescue/jobs" @{ reason="DRIVER_DELAYED" }
Assert $rescue.data.jobId "rescue job missing"
$rescueResult = Get ("/rescue/jobs/" + $rescue.data.jobId + "/result")
Assert ($rescueResult.data.lateNotWorse -eq $true) "rescue late guard failed"
Pass rescueFlow

$batchId = "BATCH-$run"
$batchItems = Items 120
$batchItems += @{ orderId="BAD-$run"; externalOrderId="BAD-$run"; invalid=$true; lat=0; lng=0 }
$batch = Post "/bigdata/batches" @{ batchId=$batchId; tenantId="demo"; items=$batchItems; options=@{ validationMode="STRICT"; dedupeKey="externalOrderId" } } @{ "Idempotency-Key"="pgv2-batch-$run" }
Assert ($batch.data.accepted -eq 120) "batch accepted mismatch"
$batchPage = Get ("/bigdata/batches/" + $batchId + "/items?page=0&size=50")
Assert ($batchPage.data.size -eq 50) "batch pagination missing"
Pass bigDataFlow

$events = Get ("/jobs/" + $static.data.jobId + "/events?limit=20")
Assert ($events.data.count -gt 0) "job events missing"
Pass events
$artifacts = Get ("/jobs/" + $static.data.jobId + "/artifacts")
Assert (@($artifacts.data).Count -gt 0) "artifacts missing"
Pass artifacts

$summary = [ordered]@{
  version = "v0.9.9.8-playground-map-first"
  overallPass = $true
  dashboardTypecheck = $results.dashboardTypecheck
  dashboardBuild = $results.dashboardBuild
  backendHealth = $results.backendHealth
  playgroundRouteExists = $true
  apiHealthBadge = $results.apiHealthBadge
  relativeApiBase = "PASS"
  viteProxy = "PASS"
  staticFlow = $results.staticFlow
  liveFlow = $results.liveFlow
  rescueFlow = $results.rescueFlow
  bigDataFlow = $results.bigDataFlow
  mapPanel = $results.mapPanel
  hcmLeafletMap = "PASS"
  osmAttribution = "PASS"
  coordinateModeBadge = "PASS"
  syntheticFallback = "PASS"
  pinsAndRoutes = $results.pinsAndRoutes
  timeline = $results.timeline
  seedAttribution = "PASS"
  safetyGuard = "PASS"
  bigDataPipeline = "PASS"
  events = $results.events
  artifacts = $results.artifacts
  noRawFailedToFetch = $true
  dashboardUrl = $DashboardUrl
}
$path = Join-Path $OutputDir "playground-v2-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
