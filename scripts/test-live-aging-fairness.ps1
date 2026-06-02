param(
  [string]$BaseUrl = "http://localhost:18116"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost($Path, $Body) {
  Invoke-RestMethod -Method Post "$BaseUrl$Path" -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10)
}

Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/start" | Out-Null

$nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$oldPlacedAtMs = $nowMs - 65000
$suffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)

$oldBadOrder = @{
  tenantId = "demo"
  regionId = "hcmc-aging-$suffix"
  externalOrderId = "AGING-BAD-OLD-$suffix"
  placedAtMs = $oldPlacedAtMs
  pickupLat = 10.751
  pickupLng = 106.671
  dropoffLat = 10.900
  dropoffLng = 106.900
  priority = 1
  urgent = $false
  promisedEtaMinutes = 60
}
Invoke-JsonPost "/api/v1/live/orders" $oldBadOrder | Out-Null

for ($i = 1; $i -le 5; $i++) {
  $order = @{
    tenantId = "demo"
    regionId = "hcmc-aging-$suffix"
    externalOrderId = "AGING-GOOD-$suffix-$i"
    placedAtMs = $nowMs
    pickupLat = 10.751 + ($i * 0.0002)
    pickupLng = 106.671 + ($i * 0.0002)
    dropoffLat = 10.756 + ($i * 0.0002)
    dropoffLng = 106.676 + ($i * 0.0002)
    priority = 2
    urgent = $false
    promisedEtaMinutes = 45
  }
  Invoke-JsonPost "/api/v1/live/orders" $order | Out-Null
}

Start-Sleep -Seconds 1
$beforeState = Invoke-RestMethod "$BaseUrl/api/v1/live/state"
$beforeCycles = [int]$beforeState.data.completedCycles
Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/cycles/run-now" | Out-Null
for ($attempt = 1; $attempt -le 10; $attempt++) {
  $state = Invoke-RestMethod "$BaseUrl/api/v1/live/state"
  $cycleId = $state.data.lastCycleId
  if ($cycleId -and ([int]$state.data.completedCycles) -gt $beforeCycles) { break }
  Start-Sleep -Milliseconds 500
}
$cycle = Invoke-RestMethod "$BaseUrl/api/v1/live/cycles/$cycleId"
$selection = $cycle.data.selection

$checks = [ordered]@{
  fairPolicy = $selection.selectionPolicy -eq "GRAPH_VALUE_FAIR_BATCH_SELECTION"
  persistentAging = $selection.agingPolicy -eq "ORDER_PLACED_AT_PERSISTENT_AGING"
  starvationGuard = $selection.starvationGuardApplied -eq $true
  forcedOldOrder = $selection.forcedOrderCount -ge 1
  oldAgePreserved = $selection.oldestOrderAliveMs -ge 60000
  badOrderVisible = $selection.badOrderCount -ge 1
}

$failed = $checks.GetEnumerator() | Where-Object { -not $_.Value } | Select-Object -ExpandProperty Key
$result = [ordered]@{ ok = $failed.Count -eq 0; failed = $failed; state = $state.data; selection = $selection; cycle = $cycle.data }
$result | ConvertTo-Json -Depth 20
if ($failed.Count -gt 0) { exit 1 }
