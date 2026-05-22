param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$PlaygroundDir = "playground",
  [string]$OutputDir = "artifacts/test-reports/v1.1.0-control-tower-ui"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summary = [ordered]@{
  version = "v1.1.0-control-tower-ui"
  startedAt = (Get-Date).ToString("o")
}

function Set-Pass($Name, $Value = "PASS") { $script:summary[$Name] = $Value }
function Set-Fail($Name, $Message) { $script:summary[$Name] = "FAIL: $Message"; throw "$Name failed: $Message" }

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo"; "Content-Type" = "application/json"; "Idempotency-Key" = "ct-ui-$([Guid]::NewGuid())" }
  $uri = "$BaseUrl$Path"
  if ($Body -ne $null) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body ($Body | ConvertTo-Json -Depth 40)
  }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
}

function Get-FirstId($Object, [string[]]$Keys) {
  foreach ($key in $Keys) {
    if ($Object.PSObject.Properties.Name -contains $key -and $Object.$key) { return [string]$Object.$key }
  }
  return $null
}

try {
  $health = Invoke-Irx "/v1/health"
  $version = Invoke-Irx "/v1/version"
  if (($health.status -ne "UP") -and (-not $health.externalSolvers)) { Set-Fail "backendHealth" "health response is not UP" }
  Set-Pass "backendHealth"
  $summary.versionResponse = $version

  $solver = $health.externalSolvers
  if (-not $solver) { Set-Fail "solverReadiness" "externalSolvers missing" }
  if ($solver.vroom -ne "AVAILABLE") { Set-Fail "solverReadiness" "VROOM=$($solver.vroom)" }
  if ($solver.ortools -ne "AVAILABLE") { Set-Fail "solverReadiness" "ORTOOLS=$($solver.ortools)" }
  if ($solver.pyvrp -ne "AVAILABLE") { Set-Fail "solverReadiness" "PYVRP=$($solver.pyvrp)" }
  if ($health.adaptiveMl.qualitySeeking -ne $true) { Set-Fail "solverReadiness" "adaptiveMl.qualitySeeking is not true" }
  Set-Pass "solverReadiness"

  Push-Location $PlaygroundDir
  npm install | Out-Host
  if ($LASTEXITCODE -ne 0) { Set-Fail "frontendInstall" "npm install failed" }
  Set-Pass "frontendInstall"
  npm run typecheck | Out-Host
  if ($LASTEXITCODE -ne 0) { Set-Fail "frontendTypecheck" "npm run typecheck failed" }
  Set-Pass "frontendTypecheck"
  npm run build | Out-Host
  if ($LASTEXITCODE -ne 0) { Set-Fail "frontendBuild" "npm run build failed" }
  Set-Pass "frontendBuild"
  Pop-Location

  $scanFiles = Get-ChildItem -Path (Join-Path $PlaygroundDir "src") -Recurse -Include *.ts,*.tsx
  $blocked = @("41.51", "42.13", "45.07", "sampleResponse", "executeJavaPipeline", "makeRandomLiveOrder", "demoData", "DRV_ALPHA", "DRV_BETA", "routesFromResult(null")
  $hits = @()
  foreach ($pattern in $blocked) {
    $hits += Select-String -Path $scanFiles.FullName -Pattern ([regex]::Escape($pattern)) -ErrorAction SilentlyContinue
  }
  $setTimeoutHits = Select-String -Path $scanFiles.FullName -Pattern "setTimeout" -ErrorAction SilentlyContinue
  if ($setTimeoutHits) { $hits += $setTimeoutHits }
  $randomHits = Select-String -Path $scanFiles.FullName -Pattern "Math\.random" -ErrorAction SilentlyContinue
  if ($randomHits) { $hits += $randomHits }
  if ($hits.Count -gt 0) {
    $summary.mockHardcodeScanHits = $hits | Select-Object Path,LineNumber,Line
    Set-Fail "mockHardcodeScan" "blocked mock/hardcode patterns found"
  }
  Set-Pass "mockHardcodeScan"

  $staticBody = @{ requestId="ct-ui-static-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; datasetId="raw-s"; profile="QUALITY_SEEKING"; adaptiveMl=@{ enabled=$true; mode="QUALITY_SEEKING"; topKMoves=80; explorationRate=0.2; qualityBudgetMs=5000 }; options=@{ maxRuntimeMs=60000; returnDiagnostics=$true } }
  $job = Invoke-Irx "/v1/dispatch/jobs" "POST" $staticBody
  $jobId = Get-FirstId $job @("jobId", "id")
  $executionId = Get-FirstId $job @("executionId")
  if (-not $jobId) { Set-Fail "staticDispatchUiFlow" "jobId missing" }
  if (-not $executionId) { $executionId = $jobId; $summary.executionIdFallback = "jobId" }
  $status = Invoke-Irx "/v1/dispatch/jobs/$jobId"
  $result = Invoke-Irx "/v1/dispatch/jobs/$jobId/result"
  if (-not $result.finalSolver) { Set-Fail "staticDispatchUiFlow" "finalSolver missing" }
  if (-not $result.routes) { Set-Fail "staticDispatchUiFlow" "routes missing" }
  if (-not $result.metrics) { Set-Fail "staticDispatchUiFlow" "metrics missing" }
  $summary.staticStatus = $status.status
  Set-Pass "staticDispatchUiFlow"

  $timeline = Invoke-Irx "/v1/executions/$executionId/timeline"
  $events = Invoke-Irx "/v1/executions/$executionId/events"
  $timelineText = ($timeline | ConvertTo-Json -Depth 50)
  $stageGroups = @(
    @("INPUT_VALIDATION"),
    @("MATRIX_BUILDING", "MATRIX"),
    @("SEED_GENERATION", "SEED_ARCHIVE"),
    @("BASELINE_SOLVERS_RUNNING", "ROUTE_CONSTRUCTION"),
    @("ADAPTIVE_ML_POLICY"),
    @("DOMINANCE_GUARD"),
    @("FINAL_RESULT", "FINAL_SOLUTION"),
    @("COMPLETED")
  )
  $missingStages = @()
  foreach ($group in $stageGroups) {
    $present = $false
    foreach ($stageName in $group) { if ($timelineText -match $stageName) { $present = $true } }
    if (-not $present) { $missingStages += ($group -join "/") }
  }
  if ($missingStages.Count -gt 0) { Set-Fail "executionTimeline" "missing stages: $($missingStages -join ', ')" }
  $summary.executionEventsCount = if ($events.events) { @($events.events).Count } else { 0 }
  Set-Pass "executionTimeline"

  $compareBody = @{ requestId="ct-ui-compare-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; datasetId="raw-s"; profile="QUALITY_SEEKING"; solvers=@("IRX","VROOM","ORTOOLS","PYVRP"); options=@{ maxRuntimeMs=60000; returnDiagnostics=$true } }
  $compare = Invoke-Irx "/v1/compare/jobs" "POST" $compareBody
  $compareJobId = Get-FirstId $compare @("jobId", "id")
  if (-not $compareJobId) { Set-Fail "compareUiFlow" "compare jobId missing" }
  $compareResult = Invoke-Irx "/v1/compare/jobs/$compareJobId/result"
  $compareText = ($compareResult | ConvertTo-Json -Depth 60)
  foreach ($solverName in @("IRX_NATIVE", "IRX_HYBRID_FINAL", "VROOM", "ORTOOLS", "PYVRP")) {
    if ($compareText -notmatch $solverName) { Set-Fail "compareUiFlow" "$solverName missing from compare result" }
  }
  if ($compareResult.solvers.IRX_NATIVE.runtimeMs -lt 1) { Set-Fail "compareUiFlow" "IRX_NATIVE runtimeMs must be >= 1" }
  if ($compareResult.solvers.IRX_HYBRID_FINAL.runtimeMs -lt 1) { Set-Fail "compareUiFlow" "IRX_HYBRID_FINAL runtimeMs must be >= 1" }
  Set-Pass "compareUiFlow"

  $live = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId="ct-ui-live-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; cityId="hcm"; profile="LIVE_ROLLING"; rollingConfig=@{ freezeNextStop=$true; freezePickedOrders=$true } }
  $sessionId = Get-FirstId $live @("sessionId", "id")
  if (-not $sessionId) { Set-Fail "liveDynamicUiFlow" "sessionId missing" }
  $order = @{ orderId="ct-ui-order-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; load=4; pickup=@{ lat=10.7626; lng=106.6601 }; dropoff=@{ lat=10.7812; lng=106.6923 }; deadline=(Get-Date).AddMinutes(45).ToString("o") }
  Invoke-Irx "/v1/live/sessions/$sessionId/orders" "POST" @{ requestId="ct-ui-order-req-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; order=$order } | Out-Null
  $cycle = Invoke-Irx "/v1/live/sessions/$sessionId/cycles" "POST" @{ trigger="MANUAL"; reason="control-tower-ui-gate"; options=@{ maxRuntimeMs=5000; returnDiagnostics=$true } }
  $state = Invoke-Irx "/v1/live/sessions/$sessionId/state"
  $stateText = ($state | ConvertTo-Json -Depth 60)
  if ($stateText -notmatch "routes") { Set-Fail "liveDynamicUiFlow" "live state has no routes" }
  $summary.liveCycleStatus = $cycle.status
  Set-Pass "liveDynamicUiFlow"

  $sandbox = Invoke-Irx "/v1/dispatch/jobs" "POST" $staticBody
  if (-not (Get-FirstId $sandbox @("jobId", "id"))) { Set-Fail "apiSandbox" "dispatch sandbox request did not return jobId" }
  Set-Pass "apiSandbox"

  $summary.overallPass = $true
} catch {
  try { Pop-Location } catch {}
  $summary.overallPass = $false
  $summary.error = $_.Exception.Message
}

$summary.finishedAt = (Get-Date).ToString("o")
$path = Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 80 | Set-Content $path -Encoding UTF8
Write-Output "SUMMARY=$path"
if (-not $summary.overallPass) { exit 1 }
