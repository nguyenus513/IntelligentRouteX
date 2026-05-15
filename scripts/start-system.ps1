$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Dashboard = Join-Path $Root "dashboard"
$BackendUrl = "http://localhost:8080/api/v1/dispatch/health"
$FrontendUrl = "http://localhost:5173"
$SpringProfile = "dispatch-v2-full-adaptive"
$MaterializationRoot = "E:\irx-materialization"
$ModelManifest = Join-Path $Root "services\models\model-manifest.yaml"
$GradleUserHome = Join-Path $Root ".gradle-user"
$FeedbackRoot = Join-Path $MaterializationRoot "dispatch-v2-feedback"

$SpringArgs = @(
    "--spring.profiles.active=$SpringProfile",
    "--routechain.dispatch-v2.sidecar-required=true",
    "--routechain.dispatch-v2.ml-enabled=true",
    "--routechain.dispatch-v2.ml.tabular.enabled=true",
    "--routechain.dispatch-v2.ml.routefinder.enabled=true",
    "--routechain.dispatch-v2.ml.greedrl.enabled=true",
    "--routechain.dispatch-v2.ml.forecast.enabled=true",
    "--routechain.dispatch-v2.selector-ortools-enabled=true",
    "--routechain.dispatch-v2.tomtom-enabled=false",
    "--routechain.dispatch-v2.traffic.enabled=false",
    "--routechain.dispatch-v2.open-meteo-enabled=false",
    "--routechain.dispatch-v2.weather.enabled=false",
    "--routechain.dispatch-v2.feedback.base-dir=$($FeedbackRoot -replace '\\','/')",
    "--routechain.dispatch-v2.warm-hot-start.load-latest-snapshot-on-boot=false",
    "--routechain.dispatch-v2.context.timeouts.eta-ml-timeout=5s",
    "--routechain.dispatch-v2.pair.ml-timeout=5s",
    "--routechain.dispatch-v2.ml.tabular.read-timeout=5s",
    "--routechain.dispatch-v2.ml.routefinder.read-timeout=5s",
    "--routechain.dispatch-v2.ml.routefinder.alternatives-timeout=5s",
    "--routechain.dispatch-v2.ml.routefinder.refine-timeout=5s",
    "--routechain.dispatch-v2.ml.greedrl.read-timeout=5s",
    "--routechain.dispatch-v2.ml.greedrl.bundle-timeout=5s",
    "--routechain.dispatch-v2.ml.greedrl.sequence-timeout=5s",
    "--routechain.dispatch-v2.ml.forecast.read-timeout=8s",
    "--routechain.dispatch-v2.selector.ortools.timeout=5s",
    "--routechain.dispatch-v2.ml.model-manifest-path=$($ModelManifest -replace '\\','/')"
) -join " "

function Test-Http($Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-Http($Name, $Url, $Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Http $Url) {
            Write-Host "$Name ready: $Url" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Host "$Name not ready yet: $Url" -ForegroundColor Yellow
    return $false
}

function Stop-LegacyAndroidDashboard {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like "*android-app*admin-dashboard*" -or $_.CommandLine -like "*admin-dashboard*android-app*" } |
        ForEach-Object {
            Write-Host "Stopping legacy Android admin dashboard PID $($_.ProcessId)" -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Start-Worker($Name, $Directory, $Port, $ExtraEnv = @{}) {
    $healthUrl = "http://127.0.0.1:$Port/health"
    if (Test-Http $healthUrl) {
        Write-Host "$Name worker already running: $healthUrl" -ForegroundColor Green
        return
    }
    $workerDir = Join-Path $Root $Directory
    $envCmd = "`$env:IRX_MODEL_MANIFEST_PATH='$ModelManifest'; `$env:TEMP='$MaterializationRoot\tmp'; `$env:TMP='$MaterializationRoot\tmp'; `$env:PIP_CACHE_DIR='$MaterializationRoot\pip-cache';"
    foreach ($key in $ExtraEnv.Keys) {
        $envCmd += " `$env:$key='$($ExtraEnv[$key])';"
    }
    $command = "cd '$workerDir'; $envCmd py -3 -m uvicorn app:app --host 127.0.0.1 --port $Port"
    Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $command) -WindowStyle Normal
}

function Assert-WorkerReady($Name, $Port, $TimeoutSeconds = 180) {
    $readyUrl = "http://127.0.0.1:$Port/ready"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $reason = "not-called"
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod -Uri $readyUrl -TimeoutSec 20
            if ($ready.ready -eq $true) {
                Write-Host "$Name worker ready" -ForegroundColor Green
                return
            }
            $reason = $ready.reason
        } catch {
            $reason = $_.Exception.Message
        }
        Start-Sleep -Seconds 5
    }
    throw "$Name worker is not ready on $readyUrl. Reason: $reason"
}

New-Item -ItemType Directory -Force "$MaterializationRoot\tmp", "$MaterializationRoot\pip-cache", $GradleUserHome, $FeedbackRoot | Out-Null

Write-Host "Starting IntelligentRouteX full system: FULL Dispatch V2, TomTom OFF" -ForegroundColor Cyan
Stop-LegacyAndroidDashboard

Write-Host "Starting full Dispatch V2 ML workers..." -ForegroundColor Cyan
Start-Worker "Tabular" "services\ml-tabular-worker" 8091
Start-Worker "RouteFinder" "services\ml-routefinder-worker" 8092
Start-Worker "GreedRL" "services\ml-greedrl-worker" 8093 @{ IRX_GREEDRL_RUNTIME_MODE = "lite" }
Start-Worker "Forecast" "services\ml-forecast-worker" 8096

Assert-WorkerReady "Tabular" 8091
Assert-WorkerReady "RouteFinder" 8092
Assert-WorkerReady "GreedRL" 8093
Assert-WorkerReady "Forecast" 8096 600

if (-not (Test-Path (Join-Path $Dashboard "node_modules"))) {
    Write-Host "Installing dashboard dependencies..." -ForegroundColor Yellow
    Push-Location $Dashboard
    npm install
    Pop-Location
}

if (-not (Test-Http $BackendUrl)) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$Root'; `$env:GRADLE_USER_HOME='$GradleUserHome'; `$env:IRX_MODEL_MANIFEST_PATH='$ModelManifest'; .\gradlew.bat bootRun --args='$SpringArgs'"
    ) -WindowStyle Normal
} else {
    Write-Host "Backend already running: $BackendUrl" -ForegroundColor Green
}

if (-not (Test-Http $FrontendUrl)) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$Dashboard'; npm run dev -- --port 5173 --strictPort"
    ) -WindowStyle Normal
} else {
    Write-Host "Frontend already running: $FrontendUrl" -ForegroundColor Green
}

Wait-Http "Backend" $BackendUrl 90 | Out-Null
Wait-Http "Frontend" $FrontendUrl 60 | Out-Null

Write-Host "Opening dashboard..." -ForegroundColor Cyan
Start-Process $FrontendUrl
