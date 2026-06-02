param(
  [string]$BaseUrl = "http://localhost:18116",
  [int]$Orders = 6
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost($Path, $Body) {
  Invoke-RestMethod -Method Post "$BaseUrl$Path" -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10)
}

Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/start" | Out-Null

$invalid = @{ tenantId="demo"; regionId="hcmc-east"; externalOrderId="BAD-1"; pickupLat=10.75; pickupLng=106.67; promisedEtaMinutes=30 }
Invoke-JsonPost "/api/v1/live/orders" $invalid | Out-Null

for ($i = 1; $i -le $Orders; $i++) {
  $urgent = $i -eq 1
  $order = @{
    tenantId = "demo"
    regionId = "hcmc-east"
    externalOrderId = "REG-$i"
    pickupLat = 10.750 + ($i * 0.001)
    pickupLng = 106.670 + ($i * 0.001)
    dropoffLat = 10.760 + ($i * 0.001)
    dropoffLng = 106.680 + ($i * 0.001)
    priority = $(if ($urgent) { 9 } else { 2 })
    urgent = $urgent
    promisedEtaMinutes = $(if ($urgent) { 15 } else { 45 })
  }
  Invoke-JsonPost "/api/v1/live/orders" $order | Out-Null
  if ($i -eq 2) { Invoke-JsonPost "/api/v1/live/orders" $order | Out-Null }
}

Start-Sleep -Seconds 3
Invoke-RestMethod -Method Post "$BaseUrl/api/v1/live/cycles/run-now" | Out-Null
$state = Invoke-RestMethod "$BaseUrl/api/v1/live/state"
$cycleId = $state.data.lastCycleId
$cycle = Invoke-RestMethod "$BaseUrl/api/v1/live/cycles/$cycleId"

$checks = [ordered]@{
  acceptedAtLeastInput = $state.data.acceptedOrders -ge $Orders
  rejectedInvalid = $state.data.rejectedOrders -ge 1
  duplicateSkipped = $state.data.duplicateOrders -ge 1
  noFallback = $state.data.fallbackCycles -eq 0
  assignedAllValid = $state.data.assignedOrders -ge $Orders
  coreRan = $state.data.coreCycles -ge 1
  latestCore = $cycle.data.core -eq $true
  safetyPassed = $cycle.data.safetyPassed -eq $true
  repairModeDeep = $cycle.data.repairMode -eq "PD_LNS_PNS_DEEP"
  noCoreDelta = $cycle.data.coreAssignedDelta -eq 0
}

$failed = $checks.GetEnumerator() | Where-Object { -not $_.Value } | Select-Object -ExpandProperty Key
$result = [ordered]@{ ok = $failed.Count -eq 0; failed = $failed; state = $state.data; cycle = $cycle.data }
$result | ConvertTo-Json -Depth 20
if ($failed.Count -gt 0) { exit 1 }
