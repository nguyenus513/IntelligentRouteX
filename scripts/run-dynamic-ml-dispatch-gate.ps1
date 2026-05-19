param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-ml-dispatch",
  [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
function Post-Json($uri, $body) { Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec 120 }
function Get-Json($uri) { Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 120 }

if(-not $SkipCompile) { Push-Location $root; try { .\gradlew.bat compileJava --no-daemon --console=plain *> (Join-Path $out "compileJava.log") } finally { Pop-Location } }

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="dynamic-ml-gate" }
$cycles = @()
$previousAssigned = 0
$assignedRegression = 0
for($i=1; $i -le 4; $i++) {
  Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId="ORD-DYN-$i"; pickup=@{lat=10.70 + ($i/1000); lng=106.60}; dropoff=@{lat=10.80; lng=106.70 + ($i/1000)}; deadline="2026-05-20T10:30:00Z"; load=1; priority="HIGH" }) } | Out-Null
  Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.72 + ($i/1000); lng=106.62; status="EN_ROUTE"; currentStopId=if($i -gt 1){"PICKUP:ORD-DYN-1"}else{$null} } | Out-Null
  $cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
  if([int]$cycle.assigned -lt $previousAssigned) { $assignedRegression++ }
  $previousAssigned = [int]$cycle.assigned
  $cycles += $cycle
}
$state = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$cycles | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "dynamic-cycles.json")
$state | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "dynamic-state.json")
$state.events | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "dynamic-events.json")

$summary = [pscustomobject]@{
  version="v0.9.11-dynamic-ml-dispatch"; gate="dynamic-ml-dispatch"; generatedAt=(Get-Date).ToUniversalTime().ToString("o"); compileJava=if($SkipCompile){"SKIPPED"}else{"PASS"}
  completedCycles=$cycles.Count
  finalAssigned=[int]$state.assigned
  staleBufferedOrders=[int]$state.buffered
  forecastOutputUsed=(@($cycles | Where-Object { [bool]$_.forecastUsed }).Count)
  greedRlActionUsed=(@($cycles | Where-Object { $_.greedRlAction -and $_.greedRlAction -ne "KEEP" }).Count)
  triModelRepairUsed=(@($cycles | Where-Object { [bool]$_.triModelRepairUsed }).Count)
  frozenStopViolations=(@($cycles | ForEach-Object { [int]$_.diagnostics.frozenStopViolations }) | Measure-Object -Sum).Sum
  pickupDropoffViolations=(@($cycles | ForEach-Object { [int]$_.diagnostics.pickupDropoffViolations }) | Measure-Object -Sum).Sum
  capacityViolations=(@($cycles | ForEach-Object { [int]$_.diagnostics.capacityViolations }) | Measure-Object -Sum).Sum
  lateRegression=(@($cycles | ForEach-Object { [int]$_.diagnostics.lateRegression }) | Measure-Object -Sum).Sum
  dominanceFailures=(@($cycles | ForEach-Object { [int]$_.diagnostics.dominanceFailures }) | Measure-Object -Sum).Sum
  assignedRegression=$assignedRegression
  eventsEmitted=(@($state.events).Count)
  overallPass=$false
}
$summary.overallPass = $summary.completedCycles -ge 4 -and $summary.assignedRegression -eq 0 -and $summary.staleBufferedOrders -eq 0 -and $summary.forecastOutputUsed -gt 0 -and $summary.greedRlActionUsed -gt 0 -and $summary.triModelRepairUsed -gt 0 -and $summary.frozenStopViolations -eq 0 -and $summary.pickupDropoffViolations -eq 0 -and $summary.capacityViolations -eq 0 -and $summary.lateRegression -eq 0 -and $summary.dominanceFailures -eq 0
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "dynamic-ml-dispatch-summary.json")
if(-not $summary.overallPass) { throw "Dynamic ML dispatch gate FAIL" }
Write-Host "[DYNAMIC-ML] PASS summary=$(Join-Path $out 'dynamic-ml-dispatch-summary.json')"
