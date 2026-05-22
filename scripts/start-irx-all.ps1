param(
    [int]$BackendPort = 18116,
    [int]$FrontendPort = 5173,
    [int]$OsrmPort = 5001,
    [switch]$SkipOsrm,
    [switch]$NoBrowser,
    [switch]$ForcePorts,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root ".runtime"
$BackendLog = Join-Path $RuntimeDir "backend.log"
$FrontendLog = Join-Path $RuntimeDir "frontend.log"
$OsrmLog = Join-Path $RuntimeDir "osrm.log"
$SummaryPath = Join-Path $RuntimeDir "start-summary.json"
$ApiBase = "http://localhost:$BackendPort"
$FrontendBase = "http://localhost:$FrontendPort"
$OsrmBase = "http://127.0.0.1:$OsrmPort"
$Headers = @{
    "X-Api-Key" = "demo-key"
    "X-Tenant-Id" = "demo"
    "Content-Type" = "application/json"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$summary = [ordered]@{
    startedAt = (Get-Date).ToString("o")
    root = $Root.Path
    ports = [ordered]@{ backend = $BackendPort; frontend = $FrontendPort; osrm = $OsrmPort }
    checks = [ordered]@{}
    services = [ordered]@{}
    smoke = [ordered]@{}
    logs = [ordered]@{ backend = $BackendLog; frontend = $FrontendLog; osrm = $OsrmLog }
    overallPass = $false
}

function Save-Summary {
    $summary.updatedAt = (Get-Date).ToString("o")
    $summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $SummaryPath
}

function Step($Message) {
    Write-Host "[IRX] $Message" -ForegroundColor Cyan
}

function Pass($Key, $Value = $true) {
    $summary.checks[$Key] = [ordered]@{ status = "PASS"; value = $Value }
    Save-Summary
}

function Fail($Key, $Message) {
    $summary.checks[$Key] = [ordered]@{ status = "FAIL"; message = $Message }
    Save-Summary
    throw $Message
}

function Require-Command($Name, $FriendlyName = $Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { Fail $Name "$FriendlyName is required but was not found in PATH." }
    Pass $Name $cmd.Source
    return $cmd
}

function Invoke-Json($Method, $Uri, $Body = $null, $TimeoutSec = 30) {
    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        TimeoutSec = $TimeoutSec
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
    }
    return Invoke-RestMethod @params
}

function Test-Http($Uri) {
    try {
        Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 4 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-Http($Uri, $Name, $TimeoutSec = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        if (Test-Http $Uri) {
            Pass $Name $Uri
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    Fail $Name "$Name did not become ready at $Uri within ${TimeoutSec}s."
}

function Wait-ApiJson($Uri, $Name, $TimeoutSec = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try {
            $result = Invoke-Json GET $Uri $null 5
            Pass $Name $Uri
            return $result
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    Fail $Name "$Name did not return JSON at $Uri within ${TimeoutSec}s."
}

function Stop-Port($Port, $Name) {
    if (-not $ForcePorts) { return }
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $owningProcessId = $connection.OwningProcess
        if ($owningProcessId -and $owningProcessId -ne $PID) {
            Step "ForcePorts: stopping process $owningProcessId on $Name port $Port"
            Stop-Process -Id $owningProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Q($Text) {
    return '"' + ($Text -replace '"', '\"') + '"'
}

function SQ($Text) {
    return "'" + ($Text -replace "'", "''") + "'"
}

function Start-LoggedPowerShell($Name, $Command, $LogPath, $WorkingDirectory) {
    $ErrorLogPath = $LogPath -replace '\.log$', '.err.log'
    if (Test-Path $LogPath) {
        try { Remove-Item -Force $LogPath -ErrorAction Stop } catch { $LogPath = $LogPath -replace '\.log$', ("-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log") }
    }
    if (Test-Path $ErrorLogPath) {
        try { Remove-Item -Force $ErrorLogPath -ErrorAction Stop } catch { $ErrorLogPath = $ErrorLogPath -replace '\.log$', ("-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log") }
    }
    $process = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $Command) `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $LogPath `
        -RedirectStandardError $ErrorLogPath `
        -PassThru
    $summary.services[$Name] = [ordered]@{ pid = $process.Id; log = $LogPath; errorLog = $ErrorLogPath; status = "STARTING" }
    Save-Summary
    return $process
}

function Assert-Available($Health, $Path, $Name) {
    $value = $Health
    foreach ($part in $Path.Split('.')) {
        if ($null -eq $value) { break }
        $value = $value.$part
    }
    if (("$value").ToUpperInvariant() -notin @("AVAILABLE", "OK", "TRUE")) {
        Fail $Name "$Name is not available. Current value: $value"
    }
    Pass $Name $value
}

function Test-DockerReady {
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Start-DockerDesktop {
    if (Test-DockerReady) {
        Pass "dockerEngine" "running"
        return
    }
    Step "Docker engine is not ready; trying to start Docker Desktop"
    $dockerDesktopCandidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $dockerDesktopCandidates.Count) {
        if ($InstallDeps -and (Get-Command winget -ErrorAction SilentlyContinue)) {
            Step "Installing Docker Desktop with winget"
            winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Fail "dockerInstall" "winget failed to install Docker Desktop." }
            $dockerDesktopCandidates = @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe") | Where-Object { Test-Path $_ }
        }
    }
    if (-not $dockerDesktopCandidates.Count) {
        Fail "dockerEngine" "Docker Desktop is missing. Re-run start.bat -InstallDeps to install via winget, then reboot/start Docker Desktop."
    }
    Start-Process $dockerDesktopCandidates[0] | Out-Null
    $deadline = (Get-Date).AddMinutes(4)
    do {
        if (Test-DockerReady) {
            Pass "dockerEngine" "started"
            return
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)
    Fail "dockerEngine" "Docker Desktop did not become ready within 4 minutes."
}

function Pull-DockerImage($Image, $Name) {
    Step "Ensuring Docker image $Image"
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        docker pull $Image
        if ($LASTEXITCODE -ne 0) { Fail $Name "Failed to pull Docker image $Image" }
    }
    Pass $Name $Image
}

function Demo-Payload($RequestId) {
    return [ordered]@{
        requestId = $RequestId
        tenantId = "demo"
        datasetId = "controlled-hcmc"
        profile = "QUALITY_SEEKING"
        drivers = @(
            @{ driverId = "DRV_ALPHA"; lat = 10.7757; lng = 106.6673; capacity = 100 },
            @{ driverId = "DRV_BETA"; lat = 10.7938; lng = 106.7040; capacity = 100 },
            @{ driverId = "DRV_GAMMA"; lat = 10.8016; lng = 106.7107; capacity = 80 },
            @{ driverId = "DRV_DELTA"; lat = 10.7628; lng = 106.6824; capacity = 90 }
        )
        orders = @(
            @{ orderId = "ORD_001"; pickupLat = 10.7829; pickupLng = 106.6846; dropoffLat = 10.8011; dropoffLng = 106.6778; demand = 15; readyTimeMinutes = 480; deadlineMinutes = 610 },
            @{ orderId = "ORD_002"; pickupLat = 10.7820; pickupLng = 106.6932; dropoffLat = 10.7941; dropoffLng = 106.7218; demand = 20; readyTimeMinutes = 485; deadlineMinutes = 625 },
            @{ orderId = "ORD_003"; pickupLat = 10.7686; pickupLng = 106.6659; dropoffLat = 10.7739; dropoffLng = 106.6980; demand = 10; readyTimeMinutes = 490; deadlineMinutes = 640 },
            @{ orderId = "ORD_004"; pickupLat = 10.7769; pickupLng = 106.7009; dropoffLat = 10.7898; dropoffLng = 106.7112; demand = 25; readyTimeMinutes = 510; deadlineMinutes = 675 },
            @{ orderId = "ORD_005"; pickupLat = 10.7923; pickupLng = 106.7044; dropoffLat = 10.8138; dropoffLng = 106.7111; demand = 18; readyTimeMinutes = 515; deadlineMinutes = 690 },
            @{ orderId = "ORD_006"; pickupLat = 10.7594; pickupLng = 106.7043; dropoffLat = 10.7510; dropoffLng = 106.7200; demand = 12; readyTimeMinutes = 520; deadlineMinutes = 705 },
            @{ orderId = "ORD_007"; pickupLat = 10.7701; pickupLng = 106.6712; dropoffLat = 10.7855; dropoffLng = 106.6901; demand = 8; readyTimeMinutes = 525; deadlineMinutes = 720 },
            @{ orderId = "ORD_008"; pickupLat = 10.8012; pickupLng = 106.6820; dropoffLat = 10.8184; dropoffLng = 106.6897; demand = 14; readyTimeMinutes = 530; deadlineMinutes = 735 },
            @{ orderId = "ORD_009"; pickupLat = 10.8085; pickupLng = 106.7004; dropoffLat = 10.8272; dropoffLng = 106.7126; demand = 11; readyTimeMinutes = 535; deadlineMinutes = 750 },
            @{ orderId = "ORD_010"; pickupLat = 10.7487; pickupLng = 106.6618; dropoffLat = 10.7650; dropoffLng = 106.6786; demand = 16; readyTimeMinutes = 540; deadlineMinutes = 765 },
            @{ orderId = "ORD_011"; pickupLat = 10.7578; pickupLng = 106.6431; dropoffLat = 10.7799; dropoffLng = 106.6524; demand = 9; readyTimeMinutes = 545; deadlineMinutes = 780 },
            @{ orderId = "ORD_012"; pickupLat = 10.7856; pickupLng = 106.7342; dropoffLat = 10.8017; dropoffLng = 106.7448; demand = 13; readyTimeMinutes = 550; deadlineMinutes = 795 },
            @{ orderId = "ORD_013"; pickupLat = 10.8231; pickupLng = 106.6299; dropoffLat = 10.8390; dropoffLng = 106.6482; demand = 17; readyTimeMinutes = 555; deadlineMinutes = 810 },
            @{ orderId = "ORD_014"; pickupLat = 10.7308; pickupLng = 106.7049; dropoffLat = 10.7464; dropoffLng = 106.7339; demand = 7; readyTimeMinutes = 560; deadlineMinutes = 825 },
            @{ orderId = "ORD_015"; pickupLat = 10.7891; pickupLng = 106.6585; dropoffLat = 10.8052; dropoffLng = 106.6654; demand = 10; readyTimeMinutes = 565; deadlineMinutes = 840 },
            @{ orderId = "ORD_016"; pickupLat = 10.7672; pickupLng = 106.7131; dropoffLat = 10.7828; dropoffLng = 106.7280; demand = 12; readyTimeMinutes = 570; deadlineMinutes = 855 },
            @{ orderId = "ORD_017"; pickupLat = 10.8156; pickupLng = 106.7210; dropoffLat = 10.8329; dropoffLng = 106.7350; demand = 15; readyTimeMinutes = 575; deadlineMinutes = 870 },
            @{ orderId = "ORD_018"; pickupLat = 10.7425; pickupLng = 106.6815; dropoffLat = 10.7581; dropoffLng = 106.6990; demand = 9; readyTimeMinutes = 580; deadlineMinutes = 885 }
        )
        adaptiveMl = @{ enabled = $true; mode = "QUALITY_SEEKING"; topKMoves = 80; explorationRate = 0.2; qualityBudgetMs = 5000 }
        options = @{ maxRuntimeMs = 60000; returnDiagnostics = $true }
    }
}

try {
    Step "Checking required tools"
    [void](Require-Command java "Java 21")
    [void](Require-Command node "Node.js 20+")
    [void](Require-Command npm "npm")
    [void](Require-Command py "Python launcher")
    [void](Require-Command docker "Docker Desktop")

    $javaVersionText = (& cmd.exe /c "java -version 2>&1") -join "`n"
    if ($javaVersionText -notmatch 'version "21\.' -and $javaVersionText -notmatch 'openjdk version "21\.' -and $javaVersionText -notmatch 'openjdk 21\.') {
        Fail "java21" "Java 21 is required. java -version returned: $javaVersionText"
    }
    Pass "java21" ($javaVersionText.Split("`n")[0])

    Start-DockerDesktop
    Pull-DockerImage "osrm/osrm-backend:latest" "osrmImage"
    $env:VROOM_DOCKER_IMAGE = if ($env:VROOM_DOCKER_IMAGE) { $env:VROOM_DOCKER_IMAGE } else { "vroomvrp/vroom-docker:v1.14.0-rc.2" }
    Pull-DockerImage $env:VROOM_DOCKER_IMAGE "vroomDockerImage"

    $vroomCmd = Join-Path $Root "tools\vroom\vroom-docker.cmd"
    if (-not (Test-Path $vroomCmd)) { Fail "vroom" "Missing VROOM wrapper: $vroomCmd" }
    $vroomVersion = (& $vroomCmd --version 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $vroomVersion -notmatch "vroom") { Fail "vroom" "VROOM wrapper is not executable. Output: $vroomVersion" }
    Pass "vroom" $vroomVersion.Trim()
    Pass "vroomMode" "docker"

    try {
        & py -3 -c "import pyvrp, ortools" | Out-Null
        Pass "pythonPackages" "pyvrp and ortools import OK"
    } catch {
        if (-not $InstallDeps) { Fail "pythonPackages" "Python packages missing. Re-run start.bat -InstallDeps or install with: py -3 -m pip install -r required.txt" }
        Step "Installing Python requirements from required.txt"
        & py -3 -m pip install -r (Join-Path $Root "required.txt")
        if ($LASTEXITCODE -ne 0) { Fail "pythonPackages" "pip install -r required.txt failed." }
        & py -3 -c "import pyvrp, ortools" | Out-Null
        Pass "pythonPackages" "installed"
    }

    if (-not $SkipOsrm) {
        Step "Checking OSRM on port $OsrmPort"
        $osrmProbe = "$OsrmBase/route/v1/driving/106.6846,10.7829;106.7040,10.7938?overview=false"
        if (-not (Test-Http $osrmProbe)) {
            Step "Starting OSRM Docker runtime"
            $osrmScript = Join-Path $PSScriptRoot "start_local_osrm_hcmc.ps1"
            $osrmCommand = "& " + (SQ $osrmScript) + " -Port $OsrmPort"
            $osrmProcess = Start-Process -FilePath "powershell.exe" `
                -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $osrmCommand) `
                -WorkingDirectory $Root.Path `
                -RedirectStandardOutput $OsrmLog `
                -RedirectStandardError ($OsrmLog -replace '\.log$', '.err.log') `
                -Wait `
                -PassThru
            if ($osrmProcess.ExitCode -ne 0) { Fail "osrm" "OSRM startup failed with exit code $($osrmProcess.ExitCode). See $OsrmLog" }
        }
        Wait-Http $osrmProbe "osrm" 120
    } else {
        $summary.checks.osrm = [ordered]@{ status = "SKIP"; value = "-SkipOsrm" }
    }

    Step "Writing frontend env"
    $envPath = Join-Path $Root "playground\.env.local"
    @"
VITE_IRX_API_BASE=http://localhost:$BackendPort
VITE_IRX_API_KEY=demo-key
VITE_IRX_TENANT_ID=demo
"@ | Set-Content -Encoding UTF8 $envPath
    Pass "frontendEnv" $envPath

    if (-not (Test-Path (Join-Path $Root "playground\node_modules"))) {
        Step "Installing frontend npm dependencies"
        Push-Location (Join-Path $Root "playground")
        try {
            & npm install
            if ($LASTEXITCODE -ne 0) { Fail "npmInstall" "npm install failed in playground." }
            Pass "npmInstall" "completed"
        } finally {
            Pop-Location
        }
    } else {
        Pass "npmInstall" "node_modules already present"
    }

    Stop-Port $BackendPort "backend"
    Stop-Port $FrontendPort "frontend"

    Step "Starting backend IRX on port $BackendPort"
    $gradleHome = Join-Path $Root ".gradle-tmp"
    $backendCommand = "cd " + (SQ $Root.Path) + "; `$env:GRADLE_USER_HOME=" + (SQ $gradleHome) + "; `$env:VROOM_BIN=" + (SQ $vroomCmd) + "; `$env:VROOM_DOCKER_IMAGE=" + (SQ $env:VROOM_DOCKER_IMAGE) + "; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_PROVIDER='osrm'; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_BASE_URL='http://127.0.0.1:$OsrmPort'; .\gradlew.bat bootRun --args='--server.port=$BackendPort --routechain.dispatch-v2.sidecar-required=false --routechain.dispatch-v2.routing.provider=osrm --routechain.dispatch-v2.routing.base-url=http://127.0.0.1:$OsrmPort'"
    Start-LoggedPowerShell "backend" $backendCommand $BackendLog $Root.Path | Out-Null
    $health = Wait-ApiJson "$ApiBase/v1/health" "backendHealth" 240
    $summary.services.backend.status = "READY"

    Assert-Available $health "externalSolvers.vroom" "vroomReady"
    Assert-Available $health "externalSolvers.ortools" "ortoolsReady"
    Assert-Available $health "externalSolvers.pyvrp" "pyvrpReady"
    if ($health.externalSolverEvidence.vroom.version -notmatch "vroom") { Fail "vroomEvidence" "Backend health does not prove VROOM execution. Evidence: $($health.externalSolverEvidence.vroom | ConvertTo-Json -Depth 8)" }
    Pass "vroomEvidence" $health.externalSolverEvidence.vroom.version
    if ($health.realRuntimePolicy.fallbackDisabled -ne $true) { Fail "realRuntimePolicy" "Backend fallbackDisabled is not true." }
    Pass "realRuntimePolicy" $health.realRuntimePolicy

    Step "Running compare smoke against real backend"
    $compareJob = Invoke-Json POST "$ApiBase/v1/compare/jobs" (Demo-Payload "start-compare-$(Get-Date -Format yyyyMMddHHmmss)") 300
    Start-Sleep -Seconds 2
    $compareResult = Invoke-Json GET "$ApiBase/v1/compare/jobs/$($compareJob.jobId)/result" $null 300
    if ($compareResult.solvers.VROOM.reason -ne "vroom-seed-emitted") { Fail "compareVroom" "VROOM did not report vroom-seed-emitted. Reason: $($compareResult.solvers.VROOM.reason)" }
    if ($compareResult.solvers.PYVRP.reason -ne "pyvrp-seed-emitted") { Fail "comparePyvrp" "PyVRP did not report pyvrp-seed-emitted. Reason: $($compareResult.solvers.PYVRP.reason)" }
    $summary.smoke.compare = [ordered]@{ status = "PASS"; jobId = $compareJob.jobId; vroom = $compareResult.solvers.VROOM.reason; pyvrp = $compareResult.solvers.PYVRP.reason }
    Save-Summary

    Step "Running static dispatch smoke with explicit FE-style input"
    $dispatchJob = Invoke-Json POST "$ApiBase/v1/dispatch/jobs" (Demo-Payload "start-static-$(Get-Date -Format yyyyMMddHHmmss)") 180
    Start-Sleep -Seconds 2
    $dispatchResult = Invoke-Json GET "$ApiBase/v1/dispatch/jobs/$($dispatchJob.jobId)/result" $null 180
    $runtimeMs = [double]$dispatchResult.metrics.runtimeMs
    if ($runtimeMs -le 1) { Fail "staticRuntime" "Static dispatch returned runtimeMs <= 1; this looks too small for the 18-order real smoke payload." }
    $summary.smoke.staticDispatch = [ordered]@{ status = "PASS"; jobId = $dispatchJob.jobId; runtimeMs = $runtimeMs; finalSolver = $dispatchResult.finalSolver }
    Save-Summary

    Step "Starting frontend playground on port $FrontendPort"
    $frontendRoot = Join-Path $Root "playground"
    $frontendCommand = "cd " + (SQ $frontendRoot) + "; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
    Start-LoggedPowerShell "frontend" $frontendCommand $FrontendLog $frontendRoot | Out-Null
    Wait-Http $FrontendBase "frontend" 90
    $summary.services.frontend.status = "READY"

    if (-not $NoBrowser) {
        Start-Process $FrontendBase | Out-Null
        $summary.services.browser = [ordered]@{ status = "OPENED"; url = $FrontendBase }
    }

    $summary.overallPass = $true
    $summary.completedAt = (Get-Date).ToString("o")
    Save-Summary
    Step "All systems ready: $FrontendBase"
    exit 0
} catch {
    $summary.overallPass = $false
    $summary.error = $_.Exception.Message
    $summary.failedAt = (Get-Date).ToString("o")
    Save-Summary
    Write-Host "[IRX] Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[IRX] Summary: $SummaryPath" -ForegroundColor Yellow
    Write-Host "[IRX] Logs: $RuntimeDir" -ForegroundColor Yellow
    exit 1
}
