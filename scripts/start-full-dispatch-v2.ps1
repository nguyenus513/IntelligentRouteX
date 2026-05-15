$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$MaterializationRoot = "E:\irx-materialization"
$ModelManifest = Join-Path $Root "services\models\model-manifest.yaml"
$GradleUserHome = Join-Path $Root ".gradle-user"
$FeedbackRoot = Join-Path $MaterializationRoot "dispatch-v2-feedback"
$BackendUrl = "http://localhost:8080/api/v1/dispatch/health"

function Test-Http($Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Start-Worker($Name, $Directory, $Port, $ExtraEnv = @{}) {
    $healthUrl = "http://127.0.0.1:$Port/health"
    if (Test-Http $healthUrl) {
        Write-Host "$Name worker already running" -ForegroundColor Green
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

function Assert-Ready($Name, $Port, $TimeoutSeconds = 180) {
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
    throw "$Name worker is not ready: $reason"
}

function Stop-Backend() {
    $me = $PID
    Get-CimInstance Win32_Process |
        Where-Object { $_.ProcessId -ne $me -and ($_.CommandLine -like "*gradlew.bat*bootRun*" -or $_.CommandLine -like "*RouteChainApiApplication*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

New-Item -ItemType Directory -Force "$MaterializationRoot\tmp", "$MaterializationRoot\pip-cache", $GradleUserHome, $FeedbackRoot | Out-Null

Write-Host "Starting Dispatch V2 FULL power, TomTom OFF" -ForegroundColor Cyan
Start-Worker "Tabular" "services\ml-tabular-worker" 8091
Start-Worker "RouteFinder" "services\ml-routefinder-worker" 8092
Start-Worker "GreedRL" "services\ml-greedrl-worker" 8093 @{ IRX_GREEDRL_RUNTIME_MODE = "lite" }
Start-Worker "Forecast" "services\ml-forecast-worker" 8096

Assert-Ready "Tabular" 8091
Assert-Ready "RouteFinder" 8092
Assert-Ready "GreedRL" 8093
Assert-Ready "Forecast" 8096 600

Stop-Backend
$SpringArgs = @(
    "--spring.profiles.active=dispatch-v2-full-adaptive",
    "--routechain.dispatch-v2.sidecar-required=true",
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
    "--routechain.dispatch-v2.selector.ortools.timeout=5s"
) -join " "
$BackendCommand = "cd '$Root'; `$env:GRADLE_USER_HOME='$GradleUserHome'; `$env:IRX_MODEL_MANIFEST_PATH='$ModelManifest'; .\gradlew.bat bootRun --args='$SpringArgs'"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-Command", $BackendCommand) -WindowStyle Normal

$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    if (Test-Http $BackendUrl) {
        Write-Host "Backend ready: $BackendUrl" -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Seconds 5
}
throw "Backend not ready: $BackendUrl"
