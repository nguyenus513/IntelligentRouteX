$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Dashboard = Join-Path $Root "dashboard"
$ReportDir = Join-Path $Root "artifacts\test-reports"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $ReportDir "dashboard-demo-gate-$Stamp.json"
$steps = New-Object System.Collections.Generic.List[object]

function Add-Step($Name, $Status, $Details = @{}) {
    $steps.Add([ordered]@{ name = $Name; status = $Status; details = $Details }) | Out-Null
    $color = if ($Status -eq "PASS") { "Green" } elseif ($Status -eq "WARN") { "Yellow" } else { "Red" }
    Write-Host "[$Status] $Name" -ForegroundColor $color
}

function Invoke-Json($Method, $Url, $Body = $null, $TimeoutSec = 30) {
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec $TimeoutSec
    }
    return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec $TimeoutSec
}

function Run-Cmd($Name, $File, $Args, $WorkDir, $TimeoutSeconds = 120, $Env = @{}) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $File
    foreach ($arg in $Args) { [void]$psi.ArgumentList.Add($arg) }
    $psi.WorkingDirectory = $WorkDir
    foreach ($key in $Env.Keys) { $psi.Environment[$key] = [string]$Env[$key] }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($psi)
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill($true) } catch {}
        throw "$Name timed out after ${TimeoutSeconds}s"
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    if ($process.ExitCode -ne 0 -or $stderr -match "BUILD FAILED|Error: Cannot find module") {
        throw "$Name failed exit=$($process.ExitCode)`n$stdout`n$stderr"
    }
    return @{ exitCode = $process.ExitCode; stdoutTail = $stdout.Substring([Math]::Max(0, $stdout.Length - 1200)); stderrTail = $stderr.Substring([Math]::Max(0, $stderr.Length - 1200)) }
}

New-Item -ItemType Directory -Force $ReportDir | Out-Null
$startedAt = Get-Date -Format o
$failed = $false

try {
    $backend = Invoke-Json GET "http://localhost:8080/api/v1/dispatch/health" $null 10
    if ($backend.status -ne "ok") { throw "backend status=$($backend.status)" }
    Add-Step "backend health" "PASS" @{ status = $backend.status }
} catch {
    Add-Step "backend health" "FAIL" @{ error = $_.Exception.Message }
    $failed = $true
}

foreach ($worker in @(
    @{ name = "tabular"; port = 8091 },
    @{ name = "routefinder"; port = 8092 },
    @{ name = "greedrl"; port = 8093 },
    @{ name = "forecast"; port = 8096 }
)) {
    try {
        $ready = Invoke-Json GET "http://127.0.0.1:$($worker.port)/ready" $null 25
        if ($ready.ready -ne $true) { throw "ready=false reason=$($ready.reason)" }
        Add-Step "worker $($worker.name) ready" "PASS" @{ port = $worker.port }
    } catch {
        Add-Step "worker $($worker.name) ready" "FAIL" @{ port = $worker.port; error = $_.Exception.Message }
        $failed = $true
    }
}

try {
    $latestSmoke = Get-ChildItem $ReportDir -Filter "full-dispatch-v2-api-smoke*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $latestSmoke) { throw "no full-dispatch-v2-api-smoke artifact" }
    $smoke = Get-Content $latestSmoke.FullName -Raw | ConvertFrom-Json
    if ([int]$smoke.total -lt 9 -or [int]$smoke.pass -lt 9) { throw "snapshot smoke not 9/9: total=$($smoke.total) pass=$($smoke.pass)" }
    Add-Step "9 live snapshot smoke artifact" "PASS" @{ path = $latestSmoke.FullName; total = $smoke.total; pass = $smoke.pass }
} catch {
    Add-Step "9 live snapshot smoke artifact" "WARN" @{ error = $_.Exception.Message }
}

try {
    $scenario = Invoke-Json POST "http://localhost:8080/api/v1/dashboard/scenario/generate" @{ orderCount = 6; driverCount = 3; scenarioName = "demo-gate"; city = "HCM" } 30
    if (-not $scenario.scenarioId) { throw "missing scenarioId" }
    Add-Step "dashboard scenario generate" "PASS" @{ scenarioId = $scenario.scenarioId; orders = $scenario.orders.Count; drivers = $scenario.drivers.Count }

    $run = Invoke-Json POST "http://localhost:8080/api/v1/dashboard/dispatch/run" @{ scenarioId = $scenario.scenarioId } 360
    $diagText = $run.diagnostics | ConvertTo-Json -Depth 30
    $badMarkers = @("worker-not-ready", "eta-ml-unavailable", "forecast-timeout") | Where-Object { $diagText -match [regex]::Escape($_) }
    if ($run.status -ne "COMPLETED") { throw "run status=$($run.status)" }
    if ($badMarkers.Count -gt 0) { throw "critical diagnostics: $($badMarkers -join ',')" }
    Add-Step "dashboard dispatch run" "PASS" @{ runId = $run.runId; status = $run.status; routes = $run.routes.Count; batches = $run.batches.Count; runtimeMs = $run.metrics.runtimeMs }
} catch {
    Add-Step "dashboard dispatch run" "FAIL" @{ error = $_.Exception.Message }
    $failed = $true
}

try {
    $compile = Run-Cmd "compileJava" "powershell.exe" @("-NoProfile", "-Command", ".\\gradlew.bat compileJava --no-daemon --console=plain") $Root 240 @{ GRADLE_USER_HOME = (Join-Path $Root ".gradle-user") }
    Add-Step "backend compileJava" "PASS" $compile
} catch {
    Add-Step "backend compileJava" "FAIL" @{ error = $_.Exception.Message }
    $failed = $true
}

try {
    $typecheck = Run-Cmd "dashboard typecheck" "powershell.exe" @("-NoProfile", "-Command", "npm run typecheck") $Dashboard 120
    Add-Step "dashboard typecheck" "PASS" $typecheck
} catch {
    Add-Step "dashboard typecheck" "FAIL" @{ error = $_.Exception.Message }
    $failed = $true
}

try {
    $build = Run-Cmd "dashboard build" "powershell.exe" @("-NoProfile", "-Command", "npm run build") $Dashboard 120
    Add-Step "dashboard build" "PASS" $build
} catch {
    Add-Step "dashboard build" "FAIL" @{ error = $_.Exception.Message }
    $failed = $true
}

$report = [ordered]@{
    schemaVersion = "dashboard-demo-gate/v1"
    startedAt = $startedAt
    finishedAt = Get-Date -Format o
    status = if ($failed) { "FAIL" } else { "PASS" }
    steps = $steps
}
$report | ConvertTo-Json -Depth 40 | Set-Content $ReportPath -Encoding UTF8
Write-Host "Report: $ReportPath" -ForegroundColor Cyan
if ($failed) { exit 1 }
exit 0



