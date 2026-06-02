param(
    [string]$BundleRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = "data/logs/smoke",
    [int]$BackendPort = 18116,
    [int]$OsrmPort = 5001,
    [int]$TimeoutSec = 150
)

$ErrorActionPreference = "Stop"
$BundleRoot = (Resolve-Path $BundleRoot).Path
$OutputPath = Join-Path $BundleRoot $OutputDir
$SummaryPath = Join-Path $OutputPath "smoke-summary.json"
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$summary = [ordered]@{
    schemaVersion = "irx-windows-portable-smoke/v1"
    startedAt = (Get-Date).ToString("o")
    bundleRoot = $BundleRoot
    checks = [ordered]@{}
    overallPass = $false
}

function Save-Summary { $summary.updatedAt = (Get-Date).ToString("o"); $summary | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $SummaryPath }
function Pass($Name, $Value = $true) { $summary.checks[$Name] = [ordered]@{ status = "PASS"; value = $Value }; Save-Summary }
function Fail($Name, $Message) { $summary.checks[$Name] = [ordered]@{ status = "FAIL"; message = $Message }; Save-Summary; throw "[$Name] $Message" }

function Invoke-Json($Method, $Uri, $Body = $null, $Timeout = 30) {
    $headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo"; "Content-Type" = "application/json" }
    $params = @{ Method = $Method; Uri = $Uri; Headers = $headers; TimeoutSec = $Timeout }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 30) }
    Invoke-RestMethod @params
}

function Wait-Json($Uri, $Name) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try { $value = Invoke-Json GET $Uri $null 5; Pass $Name $Uri; return $value } catch { Start-Sleep -Seconds 2 }
    } while ((Get-Date) -lt $deadline)
    Fail $Name "Timeout waiting for $Uri"
}

try {
    foreach ($required in @("app/irx-backend.jar", "app/public/index.html", "runtime/jre/bin/java.exe", "runtime/python/python.exe", "runtime/vroom/vroom.exe", "runtime/osrm/osrm-routed.exe", "start-irx.bat", "stop-irx.bat")) {
        $path = Join-Path $BundleRoot $required
        if (-not (Test-Path $path)) { Fail "file-$required" "Missing required file $required" }
        Pass "file-$required" $path
    }
    if (-not (Get-ChildItem (Join-Path $BundleRoot "data/osrm") -Filter "*.osrm*" -ErrorAction SilentlyContinue)) { Fail "osrmMap" "Missing .osrm map data." }
    Pass "osrmMap"

    & (Join-Path $BundleRoot "runtime/python/python.exe") -c "import pyvrp; print('pyvrp-ok')"
    if ($LASTEXITCODE -ne 0) { Fail "pyvrpImport" "pyvrp import failed." }
    Pass "pyvrpImport"

    $osrm = Wait-Json "http://127.0.0.1:$OsrmPort/route/v1/driving/106.7009,10.7769;106.7218,10.7941?overview=false" "osrmReady"
    if ($osrm.code -ne "Ok") { Fail "osrmRoute" "OSRM did not return Ok." }
    Pass "osrmRoute" $osrm.code

    $health = Wait-Json "http://127.0.0.1:$BackendPort/v1/health" "backendReady"
    Pass "health" $health.status
    $frontend = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort" -UseBasicParsing -TimeoutSec 10
    if ($frontend.StatusCode -lt 200 -or $frontend.StatusCode -ge 400) { Fail "frontend" "Frontend HTTP status $($frontend.StatusCode)" }
    Pass "frontend" $frontend.StatusCode

    $orders = 1..18 | ForEach-Object { @{ orderId = "SMK_$($_)"; pickupLat = 10.76 + ($_ % 6) * 0.006; pickupLng = 106.66 + ($_ % 7) * 0.006; dropoffLat = 10.78 + ($_ % 5) * 0.007; dropoffLng = 106.69 + ($_ % 6) * 0.006; demand = 1; deadlineMinutes = 80 } }
    $drivers = 1..5 | ForEach-Object { @{ driverId = "SMK_DRV_$($_)"; lat = 10.76 + $_ * 0.006; lng = 106.67 + $_ * 0.006; capacity = 999 } }
    $payload = @{ requestId = "portable-smoke-$([DateTimeOffset]::Now.ToUnixTimeSeconds())"; tenantId = "demo"; datasetId = "portable-smoke"; profile = "QUALITY_SEEKING"; drivers = $drivers; orders = $orders; solvers = @("IRX", "VROOM", "ORTOOLS", "PYVRP") }
    $compareJob = Invoke-Json POST "http://127.0.0.1:$BackendPort/v1/compare/jobs" $payload 90
    Start-Sleep -Seconds 2
    $jobId = if ($compareJob.jobId) { $compareJob.jobId } else { $compareJob.data.jobId }
    if (-not $jobId) { Fail "compareJob" "No compare job id returned." }
    $compare = Invoke-Json GET "http://127.0.0.1:$BackendPort/v1/compare/jobs/$jobId/result" $null 120
    Pass "compareJob" $jobId
    Pass "compareResult" @{ finalSolver = $compare.finalSolver; metrics = $compare.metrics }

    $batch = @{ batchId = "portable-bd-$([DateTimeOffset]::Now.ToUnixTimeSeconds())"; tenantId = "demo"; items = $orders; options = @{ enqueueDispatch = $true } }
    $bd = Invoke-Json POST "http://127.0.0.1:$BackendPort/api/v1/bigdata/ingest/orders" $batch 30
    Start-Sleep -Seconds 2
    $runtime = Invoke-Json GET "http://127.0.0.1:$BackendPort/api/v1/bigdata/runtime" $null 30
    Pass "bigdataIngest" $bd
    Pass "bigdataRuntime" $runtime

    $summary.overallPass = $true
    $summary.completedAt = (Get-Date).ToString("o")
    Save-Summary
    Write-Host "SUMMARY=$SummaryPath"
    exit 0
} catch {
    $summary.overallPass = $false
    $summary.error = $_.Exception.Message
    $summary.failedAt = (Get-Date).ToString("o")
    Save-Summary
    Write-Host "SUMMARY=$SummaryPath"
    throw
}
