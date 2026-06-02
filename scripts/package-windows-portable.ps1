param(
    [string]$OutputRoot = "build/release/windows-portable",
    [string]$ReleaseRoot = "build/release",
    [string]$JreDir = $env:IRX_PORTABLE_JRE_DIR,
    [string]$PythonDir = $env:IRX_PORTABLE_PYTHON_DIR,
    [string]$VroomExe = $env:IRX_PORTABLE_VROOM_EXE,
    [string]$OsrmDir = $env:IRX_PORTABLE_OSRM_DIR,
    [string]$OsrmDataDir = $env:IRX_PORTABLE_OSRM_DATA_DIR,
    [switch]$SkipBuild,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputPath = Join-Path $Root $OutputRoot
$ReleasePath = Join-Path $Root $ReleaseRoot
$BundlePath = Join-Path $OutputPath "irx-portable-windows-x64"
$SummaryPath = Join-Path $OutputPath "package-summary.json"

function Fail($Code, $Message) {
    $summary.status = "FAILED"
    $summary.failedCode = $Code
    $summary.error = $Message
    $summary.updatedAt = (Get-Date).ToString("o")
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
    $summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $SummaryPath
    throw "[$Code] $Message"
}

function Require-Path($Path, $Name) {
    if (-not $Path -or -not (Test-Path $Path)) { Fail "MISSING_$($Name.ToUpperInvariant().Replace(' ','_'))" "$Name is required for portable release: $Path" }
    return (Resolve-Path $Path).Path
}

function Copy-Dir($Source, $Target) {
    if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    Copy-Item -Recurse -Force $Source $Target
}

function Write-Text($Path, $Content) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    $Content | Set-Content -Encoding UTF8 $Path
}

$summary = [ordered]@{
    schemaVersion = "irx-windows-portable-package/v1"
    status = "RUNNING"
    startedAt = (Get-Date).ToString("o")
    root = $Root.Path
    output = $BundlePath
    requiredSolvers = @("ORTOOLS", "PYVRP", "VROOM", "OSRM")
    checks = [ordered]@{}
    artifacts = [ordered]@{}
}

New-Item -ItemType Directory -Force -Path $OutputPath, $ReleasePath | Out-Null
if (Test-Path $BundlePath) { Remove-Item -Recurse -Force $BundlePath }
New-Item -ItemType Directory -Force -Path $BundlePath | Out-Null

if (-not $SkipBuild) {
    & (Join-Path $Root "gradlew.bat") bootJar --no-daemon
    if ($LASTEXITCODE -ne 0) { Fail "BOOTJAR_FAILED" "Gradle bootJar failed." }
    Push-Location (Join-Path $Root "playground")
    try {
        $previousApiBase = $env:VITE_IRX_API_BASE
        $env:VITE_IRX_API_BASE = ""
        if (Test-Path "node_modules") {
            npm install
            if ($LASTEXITCODE -ne 0) { Fail "NPM_INSTALL_FAILED" "npm install failed." }
        } else {
            npm ci
            if ($LASTEXITCODE -ne 0) { Fail "NPM_CI_FAILED" "npm ci failed." }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { Fail "FE_BUILD_FAILED" "Frontend build failed." }
    } finally {
        $env:VITE_IRX_API_BASE = $previousApiBase
        Pop-Location
    }
}

$libsDir = Join-Path $Root "build/libs"
if (-not (Test-Path $libsDir)) { Fail "MISSING_BACKEND_JAR" "No build/libs directory found. Run without -SkipBuild or build bootJar first." }
$jar = Get-ChildItem $libsDir -Filter "*.jar" | Where-Object { $_.Name -notlike "*-plain.jar" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $jar) { Fail "MISSING_BACKEND_JAR" "No Spring Boot jar found under build/libs." }
$frontendDist = Require-Path (Join-Path $Root "playground/dist") "frontend dist"
$jre = Require-Path $JreDir "portable JRE"
$javaExe = Require-Path (Join-Path $jre "bin/java.exe") "portable Java executable"
$python = Require-Path (Join-Path $PythonDir "python.exe") "portable Python executable"
$vroom = Require-Path $VroomExe "VROOM executable"
$osrmRouted = Require-Path (Join-Path $OsrmDir "osrm-routed.exe") "OSRM routed executable"
$osrmData = Require-Path $OsrmDataDir "prebuilt OSRM data directory"
$osrmMain = Get-ChildItem $osrmData -Filter "*.osrm*" | Select-Object -First 1
if (-not $osrmMain) { Fail "MISSING_OSRM_MAP" "OSRM data directory must contain prebuilt .osrm* files." }

& $python -c "import pyvrp; print(pyvrp.__version__ if hasattr(pyvrp, '__version__') else 'pyvrp-ok')"
if ($LASTEXITCODE -ne 0) { Fail "PYVRP_IMPORT_FAILED" "Portable Python cannot import pyvrp." }

New-Item -ItemType Directory -Force -Path (Join-Path $BundlePath "app"), (Join-Path $BundlePath "runtime") | Out-Null
Copy-Item -Force $jar.FullName (Join-Path $BundlePath "app/irx-backend.jar")
Copy-Dir $frontendDist (Join-Path $BundlePath "app/public")
New-Item -ItemType Directory -Force -Path (Join-Path $BundlePath "scripts") | Out-Null
foreach ($pyvrpScript in @("run_pyvrp_seed.py", "pyvrp_vrptw_bridge.py")) {
    Copy-Item -Force (Join-Path $Root "scripts/$pyvrpScript") (Join-Path $BundlePath "scripts/$pyvrpScript")
}
Copy-Dir $jre (Join-Path $BundlePath "runtime/jre")
Copy-Dir $PythonDir (Join-Path $BundlePath "runtime/python")
New-Item -ItemType Directory -Force -Path (Join-Path $BundlePath "runtime/vroom") | Out-Null
Copy-Item -Force $vroom (Join-Path $BundlePath "runtime/vroom/vroom.exe")
Copy-Dir $OsrmDir (Join-Path $BundlePath "runtime/osrm")
Copy-Dir $osrmData (Join-Path $BundlePath "data/osrm")
New-Item -ItemType Directory -Force -Path (Join-Path $BundlePath "data/logs"), (Join-Path $BundlePath "data/irx-lake"), (Join-Path $BundlePath "config"), (Join-Path $BundlePath "smoke") | Out-Null

$appConfig = @"
server:
  port: 18116
spring:
  web:
    resources:
      static-locations: file:app/public/
routechain:
  dispatch-v2:
    routing:
      provider: osrm
      base-url: http://127.0.0.1:5001
"@
Write-Text (Join-Path $BundlePath "config/application-portable.yml") $appConfig

$startBat = @'
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "IRX_HOME=%CD%"
set "JAVA_EXE=%IRX_HOME%\runtime\jre\bin\java.exe"
set "PYVRP_PYTHON=%IRX_HOME%\runtime\python\python.exe"
set "VROOM_BIN=%IRX_HOME%\runtime\vroom\vroom.exe"
set "IRX_ROUTING_PROVIDER=osrm"
set "IRX_ROUTING_BASE_URL=http://127.0.0.1:5001"
set "IRX_API_KEY=demo-key"
set "IRX_TENANT_ID=demo"
set "LOG_DIR=%IRX_HOME%\data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":18116"') do taskkill /PID %%a /F >nul 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5001"') do taskkill /PID %%a /F >nul 2>nul
timeout /t 1 /nobreak >nul
for %%F in ("%IRX_HOME%\data\osrm\*.osrm*") do (
  if /I "%%~xF"==".osrm" set "OSRM_FILE=%%~fF"
)
if not defined OSRM_FILE set "OSRM_FILE=%IRX_HOME%\data\osrm\hcmc-demo.osrm"
if not exist "%JAVA_EXE%" echo Missing Java runtime & exit /b 10
if not exist "%PYVRP_PYTHON%" echo Missing Python runtime & exit /b 11
if not exist "%VROOM_BIN%" echo Missing VROOM runtime & exit /b 12
if not exist "%IRX_HOME%\runtime\osrm\osrm-routed.exe" echo Missing OSRM runtime & exit /b 13
if not defined OSRM_FILE echo Missing OSRM map & exit /b 14
start "IRX OSRM" /min /D "%IRX_HOME%\data\osrm" "%IRX_HOME%\runtime\osrm\osrm-routed.exe" --algorithm ch "hcmc-demo.osrm" --port 5001 > "%LOG_DIR%\osrm.log" 2> "%LOG_DIR%\osrm.err.log"
timeout /t 3 /nobreak >nul
start "IRX Backend" /min "%JAVA_EXE%" -jar "%IRX_HOME%\app\irx-backend.jar" --spring.config.additional-location="%IRX_HOME%\config\application-portable.yml" --server.port=18116 > "%LOG_DIR%\backend.log" 2> "%LOG_DIR%\backend.err.log"
timeout /t 8 /nobreak >nul
start http://127.0.0.1:18116
echo IRX portable started. Logs: %LOG_DIR%
exit /b 0
'@
Write-Text (Join-Path $BundlePath "start-irx.bat") $startBat

$stopBat = @'
@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":18116"') do taskkill /PID %%a /F >nul 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5001"') do taskkill /PID %%a /F >nul 2>nul
echo IRX portable stopped.
'@
Write-Text (Join-Path $BundlePath "stop-irx.bat") $stopBat

$readme = @"
# IRX Portable Windows x64

Double-click `start-irx.bat`.

Bundled runtimes:
- Java 21 runtime
- Python + PyVRP
- VROOM
- OSRM + prebuilt HCMC map
- IRX backend + Control Tower UI

Open: http://127.0.0.1:18116
Logs: data/logs
Stop: stop-irx.bat
"@
Write-Text (Join-Path $BundlePath "README_PORTABLE.md") $readme

Copy-Item -Force (Join-Path $Root "scripts/smoke-windows-portable.ps1") (Join-Path $BundlePath "smoke/smoke-windows-portable.ps1") -ErrorAction SilentlyContinue

$summary.status = "PACKAGED"
$summary.checks.backendJar = $jar.FullName
$summary.checks.frontendDist = $frontendDist
$summary.checks.jre = $javaExe
$summary.checks.python = $python
$summary.checks.vroom = $vroom
$summary.checks.osrm = $osrmRouted
$summary.checks.osrmMap = $osrmMain.FullName
$summary.artifacts.bundleDir = $BundlePath

if (-not $NoZip) {
    $zip = Join-Path $ReleasePath "irx-portable-windows-x64.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path $BundlePath -DestinationPath $zip -Force
    $summary.artifacts.zip = $zip
}

$summary.completedAt = (Get-Date).ToString("o")
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $SummaryPath
Write-Host "SUMMARY=$SummaryPath"
