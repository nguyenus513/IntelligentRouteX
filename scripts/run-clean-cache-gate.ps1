param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @("raw-s", "raw-m", "random-spread", "driver-scarcity-case", "tight-deadline-case", "wide-deadline-case", "driver-imbalanced-case"),
  [int]$DatasetTimeoutSeconds = 300,
  [string]$OutputDir = "artifacts/test-reports"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Parse-CacheStats($items, [string]$Prefix = "relocate-cache-stats:") {
  $stats = [ordered]@{
    evaluatedMoves = 0
    skippedByBudget = 0
    routeEvalCacheHitRate = 0.0
    moveEvalCacheHitRate = 0.0
    legCacheHitRate = 0.0
    budgetExhaustedCount = 0
  }
  if (-not $items) { return $stats }
  $count = 0
  foreach ($item in $items) {
    if (-not ($item -is [string])) { continue }
    if (-not $item.StartsWith($Prefix)) { continue }
    $text = $item.Replace($Prefix, "")
    $map = @{}
    foreach ($part in $text.Split(',')) {
      $kv = $part.Split('=')
      if ($kv.Count -eq 2) { $map[$kv[0]] = $kv[1] }
    }
    if ($map.ContainsKey("evaluated")) { $stats.evaluatedMoves += [int]$map["evaluated"] }
    if ($map.ContainsKey("skippedByBudget")) { $stats.skippedByBudget += [int]$map["skippedByBudget"] }
    if ($map.ContainsKey("budgetExhausted") -and $map["budgetExhausted"] -eq "true") { $stats.budgetExhaustedCount++ }
    if ($map.ContainsKey("routeHitRate")) { $stats.routeEvalCacheHitRate += [double]$map["routeHitRate"] }
    if ($map.ContainsKey("moveHitRate")) { $stats.moveEvalCacheHitRate += [double]$map["moveHitRate"] }
    if ($map.ContainsKey("legHitRate")) { $stats.legCacheHitRate += [double]$map["legHitRate"] }
    $count++
  }
  if ($count -gt 0) {
    $stats.routeEvalCacheHitRate = [math]::Round($stats.routeEvalCacheHitRate / $count, 2)
    $stats.moveEvalCacheHitRate = [math]::Round($stats.moveEvalCacheHitRate / $count, 2)
    $stats.legCacheHitRate = [math]::Round($stats.legCacheHitRate / $count, 2)
  }
  return $stats
}

$rows = @()
$artifacts = @()
$seenJobs = @{}
$seenRuns = @{}

foreach ($dataset in $Datasets) {
  $started = Get-Date
  $body = @{ datasetId = $dataset; solvers = @("single-order", "distance-batching", "OR-Tools", "IntelligentRouteX") } | ConvertTo-Json
  try {
    $job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
    if ($seenJobs.ContainsKey($job.jobId)) { throw "duplicate-jobId:$($job.jobId)" }
    $seenJobs[$job.jobId] = $dataset
    $result = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec 90
    $identity = $result.diagnostics.benchmarkIdentity
    if ($identity.datasetId -ne $dataset) { throw "identity-dataset-mismatch expected=$dataset actual=$($identity.datasetId)" }
    if ($seenRuns.ContainsKey($identity.runId)) { throw "duplicate-runId:$($identity.runId)" }
    $seenRuns[$identity.runId] = $dataset
    $artifact = Join-Path $OutputDir "clean-cache-gate-$dataset-$($job.jobId).json"
    $result | ConvertTo-Json -Depth 100 | Set-Content $artifact
    $artifacts += $artifact
    $hybrid = $result.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid"
    $distance = $result.diagnostics.solverResults | Where-Object solverName -eq "Distance batching"
    $ortools = $result.diagnostics.solverResults | Where-Object solverName -eq "OR-Tools"
    $vsDistance = if ([double]$hybrid.totalDistanceKm -lt [double]$distance.totalDistanceKm) { "WIN" } elseif ([double]$hybrid.totalDistanceKm -eq [double]$distance.totalDistanceKm) { "TIE" } else { "LOSS" }
    $vsOrtools = if ([double]$hybrid.totalDistanceKm -lt [double]$ortools.totalDistanceKm) { "WIN" } elseif ([double]$hybrid.totalDistanceKm -eq [double]$ortools.totalDistanceKm) { "TIE" } else { "LOSS" }
    $cache = Parse-CacheStats $result.diagnostics.seedImprovement.relocateCacheStats "relocate-cache-stats:"
    $swapCache = Parse-CacheStats $result.diagnostics.seedImprovement.relocateCacheStats "swap-cache-stats:"
    $crossCache = Parse-CacheStats $result.diagnostics.seedImprovement.relocateCacheStats "cross-insertion-cache-stats:"
    $globalCache = $result.diagnostics.globalRoutingCache
    $stageRuntime = $result.diagnostics.stageRuntime
    $matrixSnapshot = $result.diagnostics.matrixSnapshot
    $coreStage = $result.diagnostics.coreStageTiming
    $rows += [pscustomobject]@{
      datasetId = $dataset
      jobId = $job.jobId
      runId = $identity.runId
      scenarioHash = $identity.scenarioHash
      orderCount = $identity.orderCount
      driverCount = $identity.driverCount
      runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds
      hybridKm = $hybrid.totalDistanceKm
      hybridLate = $hybrid.lateOrderCount
      distanceKm = $distance.totalDistanceKm
      distanceLate = $distance.lateOrderCount
      ortKm = $ortools.totalDistanceKm
      ortLate = $ortools.lateOrderCount
      vsDistance = $vsDistance
      vsOrtools = $vsOrtools
      dominancePassed = $result.diagnostics.baselineDominanceGuard.baselineDominancePassed
      evaluatedMoves = $cache.evaluatedMoves
      skippedByBudget = $cache.skippedByBudget
      routeEvalCacheHitRate = $cache.routeEvalCacheHitRate
      moveEvalCacheHitRate = $cache.moveEvalCacheHitRate
      legCacheHitRate = $cache.legCacheHitRate
      budgetExhaustedCount = $cache.budgetExhaustedCount
      swapAttempts = $swapCache.evaluatedMoves
      swapSkippedByBudget = $swapCache.skippedByBudget
      swapBudgetExhaustedCount = $swapCache.budgetExhaustedCount
      swapLegCacheHitRate = $swapCache.legCacheHitRate
      crossInsertionAttempts = $crossCache.evaluatedMoves
      crossInsertionSkippedByBudget = $crossCache.skippedByBudget
      crossInsertionBudgetExhaustedCount = $crossCache.budgetExhaustedCount
      crossInsertionLegCacheHitRate = $crossCache.legCacheHitRate
      routeCacheRequests = if ($globalCache) { $globalCache.routeCacheRequestDelta } else { 0 }
      routeCacheHitRate = if ($globalCache) { [math]::Round([double]$globalCache.routeCacheHitRateDelta, 2) } else { 0 }
      routeCacheSize = if ($globalCache) { $globalCache.routeCacheSize } else { 0 }
      osrmCalls = if ($globalCache) { $globalCache.osrmCalls } else { 0 }
      coreDispatchMs = if ($stageRuntime) { $stageRuntime.coreDispatchMs } else { 0 }
      benchmarkBaselinesMs = if ($stageRuntime) { $stageRuntime.benchmarkBaselinesMs } else { 0 }
      seedBindingMs = if ($stageRuntime) { $stageRuntime.seedBindingMs } else { 0 }
      hybridImprovementMs = if ($stageRuntime) { $stageRuntime.hybridImprovementMs } else { 0 }
      totalBenchmarkMs = if ($stageRuntime) { $stageRuntime.totalBenchmarkMs } else { 0 }
      matrixSnapshotCacheHit = if ($matrixSnapshot) { $matrixSnapshot.cacheHit } else { $false }
      matrixSnapshotNodeCount = if ($matrixSnapshot) { $matrixSnapshot.nodeCount } else { 0 }
      matrixSnapshotBuildMs = if ($matrixSnapshot) { $matrixSnapshot.buildMs } else { 0 }
      matrixSnapshotProvider = if ($matrixSnapshot) { $matrixSnapshot.provider } else { "" }
      matrixSnapshotRoutingMode = if ($matrixSnapshot) { $matrixSnapshot.routingMode } else { "" }
      routeProposalPoolMs = if ($coreStage) { $coreStage.routeProposalPoolMs } else { 0 }
      bundleGenerationMs = if ($coreStage) { $coreStage.bundleGenerationMs } else { 0 }
      driverShortlistMs = if ($coreStage) { $coreStage.driverShortlistMs } else { 0 }
      selectorMs = if ($coreStage) { $coreStage.selectorMs } else { 0 }
      pass = ($result.diagnostics.baselineDominanceGuard.baselineDominancePassed -and $hybrid.lateOrderCount -le $ortools.lateOrderCount)
      failReason = ""
    }
  } catch {
    $rows += [pscustomobject]@{
      datasetId = $dataset
      jobId = ""
      runId = ""
      scenarioHash = ""
      orderCount = 0
      driverCount = 0
      runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds
      hybridKm = 0
      hybridLate = 0
      distanceKm = 0
      distanceLate = 0
      ortKm = 0
      ortLate = 0
      vsDistance = "FAIL"
      vsOrtools = "FAIL"
      dominancePassed = $false
      evaluatedMoves = 0
      skippedByBudget = 0
      routeEvalCacheHitRate = 0
      moveEvalCacheHitRate = 0
      legCacheHitRate = 0
      budgetExhaustedCount = 0
      swapAttempts = 0
      swapSkippedByBudget = 0
      swapBudgetExhaustedCount = 0
      swapLegCacheHitRate = 0
      crossInsertionAttempts = 0
      crossInsertionSkippedByBudget = 0
      crossInsertionBudgetExhaustedCount = 0
      crossInsertionLegCacheHitRate = 0
      routeCacheRequests = 0
      routeCacheHitRate = 0
      routeCacheSize = 0
      osrmCalls = 0
      coreDispatchMs = 0
      benchmarkBaselinesMs = 0
      seedBindingMs = 0
      hybridImprovementMs = 0
      totalBenchmarkMs = 0
      matrixSnapshotCacheHit = $false
      matrixSnapshotNodeCount = 0
      matrixSnapshotBuildMs = 0
      matrixSnapshotProvider = ""
      matrixSnapshotRoutingMode = ""
      routeProposalPoolMs = 0
      bundleGenerationMs = 0
      driverShortlistMs = 0
      selectorMs = 0
      pass = $false
      failReason = $_.Exception.Message
    }
  }
}

$summaryPath = Join-Path $OutputDir "clean-cache-gate-summary.json"
$distanceWins = ($rows | Where-Object { $_.vsDistance -eq "WIN" }).Count
$distanceTies = ($rows | Where-Object { $_.vsDistance -eq "TIE" }).Count
$distanceLosses = ($rows | Where-Object { $_.vsDistance -eq "LOSS" }).Count
$ortWins = ($rows | Where-Object { $_.vsOrtools -eq "WIN" }).Count
$ortTies = ($rows | Where-Object { $_.vsOrtools -eq "TIE" }).Count
$ortLosses = ($rows | Where-Object { $_.vsOrtools -eq "LOSS" }).Count
[pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  identityAssertions = if (($rows | Where-Object { -not $_.pass -and $_.failReason -like "*identity*" }).Count -eq 0) { "PASS" } else { "FAIL" }
  rows = $rows
  artifacts = $artifacts
  passCount = ($rows | Where-Object pass).Count
  total = $rows.Count
  uniqueJobCount = $seenJobs.Count
  uniqueRunCount = $seenRuns.Count
  totalRuntimeMs = ($rows | Measure-Object -Property runtimeMs -Sum).Sum
  distanceSummary = [pscustomobject]@{ win = $distanceWins; tie = $distanceTies; loss = $distanceLosses }
  ortoolsSummary = [pscustomobject]@{ win = $ortWins; tie = $ortTies; loss = $ortLosses }
  lateRegressionCount = ($rows | Where-Object { $_.hybridLate -gt $_.ortLate }).Count
  dominanceFailures = ($rows | Where-Object { -not $_.dominancePassed }).Count
} | ConvertTo-Json -Depth 20 | Set-Content $summaryPath

$rows | Format-Table -AutoSize
Write-Output "SUMMARY=$summaryPath"
