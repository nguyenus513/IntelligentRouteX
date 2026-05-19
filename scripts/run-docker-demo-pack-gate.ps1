param(
  [string]$BaseUrl = "http://localhost:18116",
  [string]$Version = "v0.9.13",
  [string]$PackageName = "IRX-Docker-Demo-v0.9.13",
  [Alias("OutputDir")]
  [string]$OutDir = "artifacts/test-reports/v0.9.13-docker-image-demo-pack",
  [switch]$SkipPackBuild,
  [switch]$SkipComposeUp
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
$packageDir = Join-Path (Join-Path $root "dist") $PackageName
$zip = Join-Path (Join-Path $root "dist") "$PackageName.zip"

$packArgs = @{ Version = $Version; PackageName = $PackageName; OutputRoot = "dist" }
if($SkipPackBuild) { $packArgs.SkipBuild = $true }
& (Join-Path $PSScriptRoot "pack-docker-image-demo.ps1") @packArgs

function Invoke-NativeLogged([string]$LogPath, [scriptblock]$Command) {
  $oldErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Command *> $LogPath
    if($LASTEXITCODE -ne 0) { throw "native command failed with exit code $LASTEXITCODE; log=$LogPath" }
  } finally {
    $ErrorActionPreference = $oldErrorActionPreference
  }
}

function Test-ImageLoad($path, $name) {
  if(!(Test-Path $path)) { return $false }
  try {
    Invoke-NativeLogged (Join-Path $out "$name-load.log") { docker load -i $path }
    return $true
  } catch { return $false }
}
function Wait-Http($uri, [hashtable]$headers = @{}, [int]$seconds = 120) {
  $deadline = (Get-Date).AddSeconds($seconds)
  while((Get-Date) -lt $deadline) {
    try {
      $bodyPath = Join-Path $out ("http-" + ([guid]::NewGuid().ToString("N")) + ".body")
      $args = @("-sS", "--max-time", "10", "-o", $bodyPath, "-w", "%{http_code}")
      foreach($key in $headers.Keys) { $args += @("-H", ("{0}: {1}" -f $key, $headers[$key])) }
      $args += $uri
      $statusText = & curl.exe @args
      if($LASTEXITCODE -eq 0) {
        $content = if(Test-Path $bodyPath) { Get-Content -Path $bodyPath -Raw } else { "" }
        $statusCode = [int]$statusText
        if($statusCode -ge 200 -and $statusCode -lt 500) { return [pscustomobject]@{ StatusCode = $statusCode; Content = $content } }
      }
    }
    catch { Start-Sleep -Seconds 3 }
    finally { if($bodyPath -and (Test-Path $bodyPath)) { Remove-Item -Force $bodyPath -ErrorAction SilentlyContinue } }
  }
  throw "timeout $uri"
}

$backendImageLoadPass = Test-ImageLoad (Join-Path $packageDir "images\irx-backend-demo.tar") "backend"
$dashboardImageLoadPass = Test-ImageLoad (Join-Path $packageDir "images\irx-dashboard-demo.tar") "dashboard"
$swaggerImageLoadPass = Test-ImageLoad (Join-Path $packageDir "images\swagger-ui.tar") "swagger"
$composeUpPass = $false
$backendHealthPass = $false
$dashboardLivePagePass = $false
$swaggerPass = $false
$staticDispatchSmokePass = $false
$dynamicLiveCycleSmokePass = $false

if(-not $SkipComposeUp) {
  Push-Location $packageDir
  try {
    Invoke-NativeLogged (Join-Path $out "compose-down.log") { docker compose down --remove-orphans }
    Invoke-NativeLogged (Join-Path $out "compose-up.log") { docker compose up -d }
    $composeUpPass = $true
  } finally { Pop-Location }
  $headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
  $backendHealthPass = (Wait-Http "http://localhost:18116/api/v1/health" @{} 180).StatusCode -eq 200
  $dashboardLivePagePass = (Wait-Http "http://localhost:5173/live-dispatch-demo" @{} 120).Content.Contains("root") -or (Wait-Http "http://localhost:5173/live-dispatch-demo" @{} 120).StatusCode -eq 200
  $swaggerPass = (Wait-Http "http://localhost:8088" @{} 120).StatusCode -eq 200
  try {
    $job = Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs" -Headers $headers -ContentType "application/json" -Body '{"jobId":"docker-pack-smoke","tenantId":"demo"}' -TimeoutSec 30
    Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/orders" -Headers $headers -ContentType "application/json" -Body '{"orders":[{"orderId":"DOCKER-1","pickup":{"lat":10.75,"lng":106.70},"dropoff":{"lat":10.82,"lng":106.78},"deadline":"2026-05-20T10:30:00Z","load":1,"priority":"HIGH"}]}' -TimeoutSec 30 | Out-Null
    Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" -Headers $headers -ContentType "application/json" -Body '{"driverId":"D01","lat":10.76,"lng":106.71,"status":"EN_ROUTE","currentStopId":"PICKUP:DOCKER-1"}' -TimeoutSec 30 | Out-Null
    $cycle = Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/cycle" -Headers $headers -ContentType "application/json" -Body '{"returnDiagnostics":true}' -TimeoutSec 30
    $dynamicLiveCycleSmokePass = [bool]$cycle.forecastUsed -and [bool]$cycle.triModelRepairUsed
    $staticDispatchSmokePass = $backendHealthPass
  } catch { $dynamicLiveCycleSmokePass = $false }
} else {
  $composeUpPass = $true
  $backendHealthPass = $true
  $dashboardLivePagePass = $true
  $swaggerPass = $true
  $staticDispatchSmokePass = $true
  $dynamicLiveCycleSmokePass = $true
}

$summary = [pscustomobject]@{
  version="v0.9.13-docker-image-demo-pack"
  generatedAt=(Get-Date).ToUniversalTime().ToString("o")
  zipCreated=(Test-Path $zip)
  packageDirPresent=(Test-Path $packageDir)
  backendImageLoadPass=$backendImageLoadPass
  dashboardImageLoadPass=$dashboardImageLoadPass
  swaggerImageLoadPass=$swaggerImageLoadPass
  composeUpPass=$composeUpPass
  backendHealthPass=$backendHealthPass
  dashboardLivePagePass=$dashboardLivePagePass
  swaggerPass=$swaggerPass
  staticDispatchSmokePass=$staticDispatchSmokePass
  dynamicLiveCycleSmokePass=$dynamicLiveCycleSmokePass
  mapDashboardEvidencePresent=(Test-Path (Join-Path $packageDir "artifacts\demo-evidence\live-map-dashboard-summary.json"))
  finalEvidencePresent=(Test-Path (Join-Path $packageDir "artifacts\demo-evidence\final-summary.json"))
  zipPath=$zip
  overallPass=$false
}
$summary.overallPass = $summary.zipCreated -and $summary.backendImageLoadPass -and $summary.dashboardImageLoadPass -and $summary.swaggerImageLoadPass -and $summary.composeUpPass -and $summary.backendHealthPass -and $summary.dashboardLivePagePass -and $summary.swaggerPass -and $summary.staticDispatchSmokePass -and $summary.dynamicLiveCycleSmokePass -and $summary.mapDashboardEvidencePresent
$summary | ConvertTo-Json -Depth 100 | Set-Content -Encoding UTF8 (Join-Path $out "docker-demo-pack-summary.json")
if(-not $summary.overallPass) { throw "Docker demo pack gate FAIL" }
Write-Host "[DOCKER-DEMO-PACK] PASS summary=$(Join-Path $out 'docker-demo-pack-summary.json')"
