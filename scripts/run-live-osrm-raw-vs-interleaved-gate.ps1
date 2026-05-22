param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-osrm-raw-vs-interleaved"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }
function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 90) -TimeoutSec 180
}
function Stop-Key($Stop) { "$($Stop.type):$($Stop.orderId)" }
function Has-Interleave($Seq) {
  $seenDrop = $false
  foreach($s in $Seq){ if($s -like 'DROPOFF:*'){ $seenDrop = $true }; if($seenDrop -and $s -like 'PICKUP:*'){ return $true } }
  return $false
}
function Precedence-Valid($Seq) {
  $picked = @{}
  foreach($s in $Seq){ $parts = $s -split ':',2; if($parts.Count -ne 2){ continue }; if($parts[0] -eq 'PICKUP'){ $picked[$parts[1]] = $true }; if($parts[0] -eq 'DROPOFF' -and -not $picked.ContainsKey($parts[1])){ return $false } }
  return $true
}
$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_OSRM_FORK_A"; lat = 10.7700; lng = 106.6600; capacity = 100 },
  @{ driverId = "DRV_OSRM_FORK_B"; lat = 10.8300; lng = 106.7300; capacity = 100 }
)
$orders = @(
  @{ orderId = "ORD_OSRM_001"; pickupLat = 10.7710; pickupLng = 106.6610; dropoffLat = 10.7730; dropoffLng = 106.6630; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_002"; pickupLat = 10.7720; pickupLng = 106.6620; dropoffLat = 10.7750; dropoffLng = 106.6650; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_003"; pickupLat = 10.7740; pickupLng = 106.6640; dropoffLat = 10.7770; dropoffLng = 106.6670; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_OSRM_004"; pickupLat = 10.7760; pickupLng = 106.6660; dropoffLat = 10.7780; dropoffLng = 106.6680; demand = 1; deadlineMinutes = 120 }
)
$session = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId = "osrm-fork-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers }
foreach($order in $orders){ Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{ requestId = "osrm-fork-order-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null }
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{ requestId = "osrm-fork-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "MAX_IRX" }
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$ref = @($cycle.decisionTrace.hybridRefinement.routes)[0]
$route = @($state.activeRoutes)[0]
$seq = @($route.stops | Where-Object { $_.type -eq 'PICKUP' -or $_.type -eq 'DROPOFF' } | ForEach-Object { Stop-Key $_ })
$forks = @($ref.seedForks)
$candidates = @($ref.candidates)
$failures = @()
if ($health.routing.configuredProvider -ne 'osrm') { $failures += "routing provider is not osrm" }
if ($cycle.decisionTrace.finalSelection.selectedSource -ne "IRX_FULL_ENSEMBLE") { $failures += "final source is not IRX_FULL_ENSEMBLE" }
if ($forks.Count -lt 2) { $failures += "missing raw/interleaved seed forks" }
if (@($forks | Where-Object { $_.optimizer -eq 'RAW_BEST_SEED' }).Count -lt 1) { $failures += "missing RAW_BEST_SEED fork" }
if (@($forks | Where-Object { $_.optimizer -eq 'INTERLEAVED_PAIR_RELOCATION' }).Count -lt 1) { $failures += "missing INTERLEAVED_SEED fork" }
if (@($candidates | Where-Object { $_.optimizer -eq 'INTERLEAVED_ALNS_PDPTW' }).Count -lt 1) { $failures += "missing INTERLEAVED_ALNS_PDPTW candidate" }
if ($route.geometryMode -eq 'STRAIGHT_LINE') { $failures += "final route is straight line" }
if (@($route.polyline).Count -le 2) { $failures += "final route polyline missing" }
if (-not (Has-Interleave $seq)) { $failures += "NO_INTERLEAVED_ROUTE_FOUND" }
if (-not (Precedence-Valid $seq)) { $failures += "precedence violation" }
if (-not $ref.roadGeometryRequired) { $failures += "trace does not require road geometry" }
if ($ref.roadDistanceSource -ne 'OSRM_ROUTE_LEGS') { $failures += "trace distance source is not OSRM_ROUTE_LEGS" }
$summary = [ordered]@{
  gate = "live-osrm-raw-vs-interleaved"
  sessionId = $session.sessionId
  healthRouting = $health.routing
  seedSource = $cycle.decisionTrace.finalSelection.seedSource
  selectedSource = $cycle.decisionTrace.finalSelection.selectedSource
  selectedOptimizer = $cycle.decisionTrace.finalSelection.selectedOptimizer
  finalOptimizer = $cycle.decisionTrace.finalSelection.finalOptimizer
  roadGeometryRequired = $ref.roadGeometryRequired
  roadDistanceSource = $ref.roadDistanceSource
  seedForkCount = $forks.Count
  seedForks = $forks
  alnsCandidate = @($candidates | Where-Object { $_.optimizer -eq 'INTERLEAVED_ALNS_PDPTW' } | Select-Object -First 1)
  geometryMode = $route.geometryMode
  polylinePointCount = @($route.polyline).Count
  totalDistanceKm = $route.totalDistanceKm
  totalEtaMinutes = $route.totalEtaMinutes
  finalSequence = $seq
  interleavedPickupDropoff = Has-Interleave $seq
  precedenceValid = Precedence-Valid $seq
  failures = $failures
  overallPass = $failures.Count -eq 0
}
$summaryPath = Join-Path $OutputDir "live-osrm-raw-vs-interleaved-summary.json"
$summary | ConvertTo-Json -Depth 90 | Set-Content -Encoding UTF8 $summaryPath
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "cycle-response.json")
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "state-response.json")
Write-Host "SUMMARY=$summaryPath"
Write-Host "GEOMETRY_MODE=$($summary.geometryMode)"
Write-Host "POLYLINE_POINTS=$($summary.polylinePointCount)"
Write-Host "SEED_FORKS=$($summary.seedForkCount)"
Write-Host "FINAL_SEQUENCE=$($seq -join ' -> ')"
Write-Host "FAILURES=$($failures -join ';')"
if($failures.Count -gt 0){ exit 1 }
