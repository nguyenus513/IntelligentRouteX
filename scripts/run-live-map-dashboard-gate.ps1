param(
  [string]$BaseUrl = "http://localhost:18116",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.12-live-dashboard/live-map",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
function Post-Json($uri, $body) { Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 30) -TimeoutSec 120 }
function Get-Json($uri) { Invoke-RestMethod -Method Get -Uri $uri -Headers $headers -TimeoutSec 120 }

$dashboardBuild = "SKIPPED"
if(-not $SkipBuild) { Push-Location (Join-Path $root "dashboard"); try { npm run build *> (Join-Path $out "dashboard-build.log"); $dashboardBuild = "PASS" } finally { Pop-Location } }
$pkg = Get-Content (Join-Path $root "dashboard/package.json") -Raw | ConvertFrom-Json
$page = Get-Content (Join-Path $root "dashboard/src/live/LiveDispatchDemoPage.tsx") -Raw
$panel = Get-Content (Join-Path $root "dashboard/src/live/LiveDispatchMapPanel.tsx") -Raw
$model = Get-Content (Join-Path $root "dashboard/src/live/liveMapModel.ts") -Raw
$leaflet = Get-Content (Join-Path $root "dashboard/src/live/LiveLeafletMap.tsx") -Raw
$synthetic = Get-Content (Join-Path $root "dashboard/src/live/LiveSyntheticMap.tsx") -Raw

$job = Post-Json "$BaseUrl/api/v1/live/jobs" @{ jobId="live-map-gate"; tenantId="demo" }
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/orders" @{ orders=@(@{ orderId="MAP-ORD-1"; pickup=@{lat=10.75;lng=106.70}; dropoff=@{lat=10.82;lng=106.78}; deadline="2026-05-20T10:30:00Z"; load=1; priority="HIGH" }) } | Out-Null
Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" @{ driverId="D01"; lat=10.76; lng=106.71; status="EN_ROUTE"; currentStopId="PICKUP:MAP-ORD-1" } | Out-Null
$before = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$cycle = Post-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/cycle" @{ returnDiagnostics=$true }
$after = Get-Json "$BaseUrl/api/v1/live/jobs/$($job.jobId)/state"
$after | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-map-state.json")
$cycle | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-map-cycle.json")

$summary = [pscustomobject]@{
  version="v0.9.12-live-dashboard-map"
  gate="live-map-dashboard"
  generatedAt=(Get-Date).ToUniversalTime().ToString("o")
  dashboardBuild=$dashboardBuild
  liveMapComponentExists=(Test-Path (Join-Path $root "dashboard/src/live/LiveDispatchMapPanel.tsx"))
  leafletDependencyPresent=($pkg.dependencies.leaflet -ne $null -and $pkg.dependencies.'react-leaflet' -ne $null)
  syntheticFallbackPresent=$synthetic.Contains('data-testid="live-synthetic-map"')
  mapPanelWired=($page.Contains("LiveDispatchMapPanel") -and $panel.Contains("LiveLeafletMap") -and $panel.Contains("LiveSyntheticMap"))
  driverMarkerBinding=($model.Contains("state.drivers") -and $leaflet.Contains("kind === 'DRIVER'"))
  pickupDropoffMarkerBinding=($model.Contains("PICKUP") -and $model.Contains("DROPOFF") -and [int]$after.assigned -ge 1)
  routePolylineBinding=($leaflet.Contains("Polyline") -and $synthetic.Contains("routePath") -and @($after.routes).Count -gt 0)
  mlImpactLegendPresent=($panel.Contains("ML Impact") -and $panel.Contains("GreedRL") -and $panel.Contains("Accepted ML top-K"))
  liveCycleMapUpdate=(@($before.routes).Count -eq 0 -and @($after.routes).Count -gt 0 -and [bool]$cycle.triModelRepairUsed)
  overallPass=$false
}
$summary.overallPass = $summary.dashboardBuild -in @("PASS", "SKIPPED") -and $summary.liveMapComponentExists -and $summary.leafletDependencyPresent -and $summary.syntheticFallbackPresent -and $summary.mapPanelWired -and $summary.driverMarkerBinding -and $summary.pickupDropoffMarkerBinding -and $summary.routePolylineBinding -and $summary.mlImpactLegendPresent -and $summary.liveCycleMapUpdate
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "live-map-dashboard-summary.json")
if(-not $summary.overallPass) { throw "Live map dashboard gate FAIL" }
Write-Host "[LIVE-MAP] PASS summary=$(Join-Path $out 'live-map-dashboard-summary.json')"
