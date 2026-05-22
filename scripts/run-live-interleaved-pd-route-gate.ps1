param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/live-interleaved-pd-route"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers = @{ "X-Tenant-Id" = "demo"; "X-Api-Key" = "demo-key" }
function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $uri = "$BaseUrl$Path"
  if ($Body -eq $null) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec 30 }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 180
}
function Stop-Key($Stop) { "$($Stop.type):$($Stop.orderId)" }
function Has-Interleave($Seq) {
  $seenDrop = $false
  foreach($s in $Seq){
    if($s -like 'DROPOFF:*'){ $seenDrop = $true }
    if($seenDrop -and $s -like 'PICKUP:*'){ return $true }
  }
  return $false
}
function Precedence-Valid($Seq) {
  $picked = @{}
  foreach($s in $Seq){
    $parts = $s -split ':',2
    if($parts.Count -ne 2){ continue }
    if($parts[0] -eq 'PICKUP'){ $picked[$parts[1]] = $true }
    if($parts[0] -eq 'DROPOFF' -and -not $picked.ContainsKey($parts[1])){ return $false }
  }
  return $true
}
$health = Invoke-Irx "/v1/health"
$drivers = @(
  @{ driverId = "DRV_INTERLEAVE_A"; lat = 10.7700; lng = 106.6600; capacity = 100 },
  @{ driverId = "DRV_INTERLEAVE_B"; lat = 10.8300; lng = 106.7300; capacity = 100 }
)
# Coordinates arranged along a corridor so a legal mixed sequence is shorter:
# Driver -> P1 -> P2 -> D1 -> P3 -> D2 -> P4 -> D3 -> D4
$orders = @(
  @{ orderId = "ORD_INT_001"; pickupLat = 10.7710; pickupLng = 106.6610; dropoffLat = 10.7730; dropoffLng = 106.6630; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_INT_002"; pickupLat = 10.7720; pickupLng = 106.6620; dropoffLat = 10.7750; dropoffLng = 106.6650; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_INT_003"; pickupLat = 10.7740; pickupLng = 106.6640; dropoffLat = 10.7770; dropoffLng = 106.6670; demand = 1; deadlineMinutes = 120 },
  @{ orderId = "ORD_INT_004"; pickupLat = 10.7760; pickupLng = 106.6660; dropoffLat = 10.7780; dropoffLng = 106.6680; demand = 1; deadlineMinutes = 120 }
)
$session = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId = "interleave-session-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; cityId = "hcm"; profile = "LIVE_ROLLING"; drivers = $drivers }
foreach($order in $orders){
  Invoke-Irx "/v1/live/sessions/$($session.sessionId)/orders" "POST" @{ requestId = "interleave-order-$($order.orderId)"; tenantId = "demo"; order = $order } | Out-Null
}
$cycle = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/cycles" "POST" @{ requestId = "interleave-cycle-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId = "demo"; returnDiagnostics = $true; pdLnsMode = "MAX_IRX" }
$state = Invoke-Irx "/v1/live/sessions/$($session.sessionId)/state"
$ref = @($cycle.decisionTrace.hybridRefinement.routes)[0]
$winner = $ref.winner
$route = @($state.activeRoutes)[0]
$seq = @($route.stops | Where-Object { $_.type -eq 'PICKUP' -or $_.type -eq 'DROPOFF' } | ForEach-Object { Stop-Key $_ })
$pickupCount = @($seq | Where-Object { $_ -like 'PICKUP:*' }).Count
$dropoffCount = @($seq | Where-Object { $_ -like 'DROPOFF:*' }).Count
$failures = @()
if ($cycle.decisionTrace.finalSelection.selectedSource -ne "IRX_FULL_ENSEMBLE") { $failures += "final source is not IRX_FULL_ENSEMBLE" }
if (-not (Has-Interleave $seq)) { $failures += "NO_INTERLEAVED_ROUTE_FOUND" }
if (-not (Precedence-Valid $seq)) { $failures += "precedence violation in final sequence" }
if (-not $ref.interleavedPickupDropoff) { $failures += "trace interleavedPickupDropoff is false" }
if (-not $ref.precedenceValid) { $failures += "trace precedenceValid is false" }
if ($pickupCount -lt 4 -or $dropoffCount -lt 4) { $failures += "route does not contain 4 pickup/dropoff pairs" }
if ($ref.dominanceGuard -ne "PASS") { $failures += "dominance guard did not pass" }
$summary = [ordered]@{
  gate = "live-interleaved-pd-route"
  baseUrl = $BaseUrl
  sessionId = $session.sessionId
  healthRouting = $health.routing
  seedSource = $cycle.decisionTrace.finalSelection.seedSource
  selectedSource = $cycle.decisionTrace.finalSelection.selectedSource
  selectedOptimizer = $cycle.decisionTrace.finalSelection.selectedOptimizer
  finalOptimizer = $cycle.decisionTrace.finalSelection.finalOptimizer
  interleavedPickupDropoff = $ref.interleavedPickupDropoff
  precedenceValid = $ref.precedenceValid
  interleavingScore = $ref.interleavingScore
  dominanceGuard = $ref.dominanceGuard
  inputDistanceKm = $ref.inputDistanceKm
  outputDistanceKm = $ref.outputDistanceKm
  improvementKm = $ref.improvementKm
  winner = $winner
  finalSequence = $seq
  pickupCount = $pickupCount
  dropoffCount = $dropoffCount
  failures = $failures
  overallPass = $failures.Count -eq 0
}
$summaryPath = Join-Path $OutputDir "live-interleaved-pd-route-summary.json"
$summary | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 $summaryPath
$cycle | ConvertTo-Json -Depth 90 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "cycle-response.json")
$state | ConvertTo-Json -Depth 90 | Set-Content -Encoding UTF8 (Join-Path $OutputDir "state-response.json")
Write-Host "SUMMARY=$summaryPath"
Write-Host "INTERLEAVED=$($summary.interleavedPickupDropoff)"
Write-Host "PRECEDENCE_VALID=$($summary.precedenceValid)"
Write-Host "FINAL_SEQUENCE=$($seq -join ' -> ')"
Write-Host "FAILURES=$($failures -join ';')"
if($failures.Count -gt 0){ exit 1 }
