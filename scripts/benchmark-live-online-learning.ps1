param(
  [int]$Orders = 300,
  [int]$BasePort = 18120,
  [string]$OutDir = "artifacts/online-learning-benchmark",
  [switch]$SkipDocker,
  [switch]$SkipBuild,
  [switch]$UseKafka,
  [int]$MaxWaitSeconds = 180
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost($BaseUrl, $Path, $Body, $TimeoutSec = 30) {
  Invoke-RestMethod -Method Post "$BaseUrl$Path" -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec $TimeoutSec
}

function Get-Json($BaseUrl, $Path, $TimeoutSec = 30) {
  Invoke-RestMethod "$BaseUrl$Path" -TimeoutSec $TimeoutSec
}

function Stop-Port($Port) {
  $procIds = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $procIds) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
}

function Start-App($Port, $Mode, $OutputDir, $UseKafka) {
  Stop-Port $Port
  Start-Sleep -Seconds 1
  $jar = (Get-ChildItem build\libs\*.jar | Where-Object { $_.Name -notlike '*plain*' } | Select-Object -First 1).FullName
  if (-not $jar) { throw "No boot jar found. Run with -SkipBuild only after bootJar exists." }
  $modeDir = Join-Path $OutputDir $Mode.name
  New-Item -ItemType Directory -Force $modeDir | Out-Null
  $learningFlags = if ($Mode.enabled) {
    "--routechain.ml.online.enabled=true --routechain.ml.online.shadow-only=$($Mode.shadow.ToString().ToLowerInvariant()) --routechain.ml.online.state-file=$modeDir\policy-state.json"
  } else {
    "--routechain.ml.online.enabled=false --routechain.ml.online.state-file=$modeDir\policy-state.json"
  }
  $argLine = @(
    "-jar `"$jar`"",
    "--server.port=$Port",
    "--routechain.live-kafka.enabled=$($UseKafka.ToString().ToLowerInvariant())",
    "--routechain.dispatch-v2.streaming.bootstrap-servers=localhost:9092",
    "--routechain.live-kafka.max-orders-per-cycle=200",
    "--routechain.live-kafka.max-wait-ms=250",
    "--routechain.bigdata-lite.core.enabled=true",
    "--routechain.bigdata-lite.core.max-orders-per-chunk=100",
    "--routechain.bigdata-lite.core.timeout-ms=8000",
    $learningFlags
  ) -join " "
  Start-Process -FilePath "java" -ArgumentList $argLine -RedirectStandardOutput (Join-Path $modeDir "app.log") -RedirectStandardError (Join-Path $modeDir "app.err.log") -WindowStyle Hidden | Out-Null
  $baseUrl = "http://localhost:$Port"
  for ($i = 0; $i -lt 60; $i++) {
    try { Get-Json $baseUrl "/api/v1/live/state" 3 | Out-Null; return $baseUrl } catch { Start-Sleep -Seconds 1 }
  }
  throw "App did not become ready on port $Port"
}

function New-Order($Scenario, $ModeName, $Index, $Total) {
  $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $region = "bench-$ModeName-$Scenario"
  $cluster = $Index % 20
  $lat = 10.750 + ($cluster * 0.00035)
  $lng = 106.670 + ($cluster * 0.00035)
  $far = $Scenario -eq "ugly_mix" -and ($Index % 10) -lt 3
  $urgent = $Scenario -eq "sla_hot" -and ($Index % 10) -lt 3
  $old = $Scenario -eq "aging_starvation" -and $Index -le [Math]::Max(1, [int]($Total * 0.10))
  if ($far -or $old) {
    $dropLat = 10.870 + (($Index % 9) * 0.002)
    $dropLng = 106.870 + (($Index % 9) * 0.002)
  } else {
    $dropLat = $lat + 0.006 + (($Index % 5) * 0.00025)
    $dropLng = $lng + 0.006 + (($Index % 5) * 0.00025)
  }
  return @{
    tenantId = "demo"
    regionId = $region
    externalOrderId = "$ModeName-$Scenario-$Index-$nowMs"
    placedAtMs = $(if ($old) { $nowMs - 90000 } else { $nowMs })
    pickupLat = $lat
    pickupLng = $lng
    dropoffLat = $dropLat
    dropoffLng = $dropLng
    priority = $(if ($urgent) { 9 } elseif ($old) { 1 } else { 2 })
    urgent = $urgent
    promisedEtaMinutes = $(if ($urgent) { 15 } elseif ($far) { 60 } else { 45 })
  }
}

function Run-Scenario($BaseUrl, $Mode, $Scenario, $Orders, $MaxWaitSeconds) {
  Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/start" -TimeoutSec 20 | Out-Null
  $started = Get-Json $BaseUrl "/api/v1/live/state" 30
  $beforeAccepted = [int]$started.data.acceptedOrders
  $beforeAssigned = [int]$started.data.assignedOrders
  $beforeFallback = [int]$started.data.fallbackCycles
  $beforeTimeouts = [int]$started.data.coreTimeouts
  $sendStart = Get-Date
  for ($i = 1; $i -le $Orders; $i++) {
    Invoke-JsonPost $BaseUrl "/api/v1/live/orders" (New-Order $Scenario $Mode.name $i $Orders) 20 | Out-Null
  }
  $sendMs = [int]((Get-Date) - $sendStart).TotalMilliseconds
  $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
  do {
    Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/cycles/run-now" -TimeoutSec 120 | Out-Null
    Start-Sleep -Milliseconds 500
    $state = Get-Json $BaseUrl "/api/v1/live/state" 30
    $acceptedDelta = [int]$state.data.acceptedOrders - $beforeAccepted
    $assignedDelta = [int]$state.data.assignedOrders - $beforeAssigned
  } while ((Get-Date) -lt $deadline -and $assignedDelta -lt $acceptedDelta)
  $cycle = if ($state.data.lastCycleId) { Get-Json $BaseUrl "/api/v1/live/cycles/$($state.data.lastCycleId)" 60 } else { $null }
  $selection = if ($cycle) { $cycle.data.selection } else { $null }
  $learning = if ($cycle) { $cycle.data.onlineLearning } else { $null }
  $acceptedDelta = [int]$state.data.acceptedOrders - $beforeAccepted
  $assignedDelta = [int]$state.data.assignedOrders - $beforeAssigned
  return [ordered]@{
    mode = $Mode.name
    scenario = $Scenario
    ordersSent = $Orders
    sendMs = $sendMs
    acceptedDelta = $acceptedDelta
    assignedDelta = $assignedDelta
    coverageRate = if ($acceptedDelta -gt 0) { [Math]::Round($assignedDelta / $acceptedDelta, 4) } else { 0 }
    backlogDelta = [Math]::Max(0, $acceptedDelta - $assignedDelta)
    fallbackDelta = [int]$state.data.fallbackCycles - $beforeFallback
    timeoutDelta = [int]$state.data.coreTimeouts - $beforeTimeouts
    avgCoreRuntimeMs = $state.data.avgCoreRuntimeMs
    avgBatchSize = $state.data.avgBatchSize
    maxBatchSize = $state.data.maxBatchSize
    avgSimilarity = $state.data.avgSimilarity
    lastImprovementPercent = if ($cycle) { $cycle.data.improvementPercent } else { 0 }
    lastRepairAccepted = if ($cycle) { $cycle.data.postSolverRepair.accepted } else { $false }
    lastSafetyPassed = if ($cycle) { $cycle.data.safetyPassed } else { $false }
    lastOldestOrderAliveMs = if ($selection) { $selection.oldestOrderAliveMs } else { 0 }
    lastForcedOrderCount = if ($selection) { $selection.forcedOrderCount } else { 0 }
    onlineLearning = if ($learning) { $learning } else { $state.data.onlineLearning }
    pass = ($acceptedDelta -eq $Orders -and $assignedDelta -eq $acceptedDelta -and ([int]$state.data.coreTimeouts - $beforeTimeouts) -eq 0)
  }
}

function Summarize($Rows, $OutputDir) {
  $groups = $Rows | Group-Object { $_["mode"] }
  $summary = foreach ($group in $groups) {
    $items = $group.Group
    $accepted = ($items | ForEach-Object { [int]$_["acceptedDelta"] } | Measure-Object -Sum).Sum
    $assigned = ($items | ForEach-Object { [int]$_["assignedDelta"] } | Measure-Object -Sum).Sum
    $backlog = ($items | ForEach-Object { [int]$_["backlogDelta"] } | Measure-Object -Sum).Sum
    $fallback = ($items | ForEach-Object { [int]$_["fallbackDelta"] } | Measure-Object -Sum).Sum
    $timeouts = ($items | ForEach-Object { [int]$_["timeoutDelta"] } | Measure-Object -Sum).Sum
    $avgRuntime = ($items | ForEach-Object { [double]$_["avgCoreRuntimeMs"] } | Measure-Object -Average).Average
    $avgImprovement = ($items | ForEach-Object { [double]$_["lastImprovementPercent"] } | Measure-Object -Average).Average
    [ordered]@{
      mode = $group.Name
      scenarios = $items.Count
      accepted = $accepted
      assigned = $assigned
      backlog = $backlog
      fallback = $fallback
      timeouts = $timeouts
      avgCoreRuntimeMs = [Math]::Round($avgRuntime, 2)
      avgImprovementPercent = [Math]::Round($avgImprovement, 2)
      pass = -not ($items | Where-Object { -not $_["pass"] })
    }
  }
  $result = [ordered]@{
    schemaVersion = "irx-online-learning-benchmark/v1"
    createdAt = [DateTimeOffset]::UtcNow.ToString("o")
    ordersPerScenario = $Orders
    rows = $Rows
    summary = $summary
    pass = -not ($summary | Where-Object { -not $_.pass })
  }
  $jsonPath = Join-Path $OutputDir "result.json"
  $mdPath = Join-Path $OutputDir "summary.md"
  $result | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 $jsonPath
  $lines = @("# IRX Online Learning Benchmark", "", "| Mode | Accepted | Assigned | Backlog | Fallback | Timeouts | Avg Core ms | Avg Improvement % | Pass |", "|---|---:|---:|---:|---:|---:|---:|---:|---|")
  foreach ($item in $summary) {
    $lines += "| $($item.mode) | $($item.accepted) | $($item.assigned) | $($item.backlog) | $($item.fallback) | $($item.timeouts) | $($item.avgCoreRuntimeMs) | $($item.avgImprovementPercent) | $($item.pass) |"
  }
  $lines | Set-Content -Encoding UTF8 $mdPath
  return $result
}

if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Force $OutDir | Out-Null
if ($UseKafka -and -not $SkipDocker) { docker compose --profile optional-kafka --profile optional-persistent up -d kafka postgres | Out-Null }
if (-not $SkipBuild) { .\gradlew.bat bootJar -x test --no-daemon --console=plain | Out-Null }

$modes = @(
  @{ name = "baseline"; enabled = $false; shadow = $false },
  @{ name = "shadow"; enabled = $true; shadow = $true },
  @{ name = "assist"; enabled = $true; shadow = $false }
)
$scenarios = @("normal", "ugly_mix", "sla_hot", "aging_starvation")
$rows = @()
$port = $BasePort
foreach ($mode in $modes) {
  $baseUrl = Start-App $port $mode $OutDir $UseKafka
  foreach ($scenario in $scenarios) {
    $rows += Run-Scenario $baseUrl $mode $scenario $Orders $MaxWaitSeconds
  }
  Stop-Port $port
  $port++
}

$result = Summarize $rows $OutDir
$result | ConvertTo-Json -Depth 50
if (-not $result.pass) { exit 1 }
