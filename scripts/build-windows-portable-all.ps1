param(
    [string]$RuntimeRoot = "C:\runtimes",
    [switch]$ForceRuntime,
    [switch]$SkipInstaller,
    [switch]$SkipMapBuild
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeRootFull = [System.IO.Path]::GetFullPath($RuntimeRoot)

$prepareArgs = @("-RuntimeRoot", $runtimeRootFull)
if ($ForceRuntime) { $prepareArgs += "-Force" }
if ($SkipMapBuild) { $prepareArgs += "-SkipMapBuild" }

& (Join-Path $Root "scripts/prepare-windows-portable-runtimes.ps1") @prepareArgs
if ($LASTEXITCODE -ne 0) { throw "Runtime preparation failed." }

$gateArgs = @(
    "-JreDir", (Join-Path $runtimeRootFull "jre-21"),
    "-PythonDir", (Join-Path $runtimeRootFull "python-pyvrp"),
    "-VroomExe", (Join-Path $runtimeRootFull "vroom\vroom.exe"),
    "-OsrmDir", (Join-Path $runtimeRootFull "osrm"),
    "-OsrmDataDir", (Join-Path $runtimeRootFull "osrm-hcmc")
)
if ($SkipInstaller) { $gateArgs += "-SkipInstaller" }

& (Join-Path $Root "scripts/run-windows-portable-release-gate.ps1") @gateArgs
if ($LASTEXITCODE -ne 0) { throw "Windows portable release gate failed." }

Write-Host "BUNDLE=$(Join-Path $Root 'build/release/windows-portable/irx-portable-windows-x64')"
Write-Host "ZIP=$(Join-Path $Root 'build/release/irx-portable-windows-x64.zip')"
Write-Host "INSTALLER=$(Join-Path $Root 'build/release/IRX-ControlTower-Setup.exe')"
