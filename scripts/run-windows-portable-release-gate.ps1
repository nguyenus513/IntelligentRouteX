param(
    [string]$JreDir = $env:IRX_PORTABLE_JRE_DIR,
    [string]$PythonDir = $env:IRX_PORTABLE_PYTHON_DIR,
    [string]$VroomExe = $env:IRX_PORTABLE_VROOM_EXE,
    [string]$OsrmDir = $env:IRX_PORTABLE_OSRM_DIR,
    [string]$OsrmDataDir = $env:IRX_PORTABLE_OSRM_DATA_DIR,
    [string]$BundleRoot = "build/release/windows-portable/irx-portable-windows-x64",
    [int]$BackendPort = 18116,
    [int]$OsrmPort = 5001,
    [switch]$SkipInstaller,
    [switch]$SkipSmokeStart
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReportDir = Join-Path $Root "artifacts/test-reports/windows-portable-release-gate"
$SummaryPath = Join-Path $ReportDir "summary.json"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$summary = [ordered]@{
    schemaVersion = "irx-windows-portable-release-gate/v1"
    startedAt = (Get-Date).ToString("o")
    root = $Root.Path
    stages = @()
    artifacts = [ordered]@{}
}

function Save-Summary {
    $summary.updatedAt = (Get-Date).ToString("o")
    $summary | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $SummaryPath
}

function Run-Stage($Name, [scriptblock]$Body) {
    Write-Host "[GATE] $Name"
    $started = Get-Date
    try {
        & $Body
        $summary.stages += [ordered]@{ name = $Name; status = "PASS"; runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds }
        Save-Summary
    } catch {
        $summary.stages += [ordered]@{ name = $Name; status = "FAIL"; runtimeMs = [int]((Get-Date) - $started).TotalMilliseconds; error = $_.Exception.Message }
        $summary.overallPass = $false
        $summary.failedStage = $Name
        Save-Summary
        throw
    }
}

function Invoke-Step($Command, $StepArgs, $WorkDir = $Root.Path) {
    Push-Location $WorkDir
    try {
        $resolvedCommand = $Command
        if (-not (Test-Path $resolvedCommand)) {
            $foundCommand = Get-Command $Command -ErrorAction SilentlyContinue
            if ($foundCommand) { $resolvedCommand = $foundCommand.Source }
        }
        $global:LASTEXITCODE = 0
        if ($resolvedCommand.ToString().EndsWith(".ps1", [System.StringComparison]::OrdinalIgnoreCase)) {
            & powershell.exe -ExecutionPolicy Bypass -File $resolvedCommand @StepArgs
        } else {
            & $resolvedCommand @StepArgs
        }
        if ($LASTEXITCODE -ne 0) { throw "$Command exited with $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

Run-Stage "git-working-tree-report" {
    $status = git -C $Root.Path status --short
    $status | Set-Content -Encoding UTF8 (Join-Path $ReportDir "git-status.txt")
    $summary.artifacts.gitStatus = Join-Path $ReportDir "git-status.txt"
}

Run-Stage "backend-compile" {
    Invoke-Step (Join-Path $Root "gradlew.bat") @("compileJava", "-x", "test", "--no-daemon", "--console=plain")
}

Run-Stage "frontend-typecheck-build" {
    Invoke-Step "npm" @("run", "typecheck") (Join-Path $Root "playground")
    Invoke-Step "npm" @("run", "build") (Join-Path $Root "playground")
}

Run-Stage "source-baseline-smoke" {
    Invoke-Step (Join-Path $Root "scripts/smoke-package-baseline.ps1") @()
}

Run-Stage "runtime-preflight" {
    Invoke-Step (Join-Path $Root "scripts/check-windows-portable-runtimes.ps1") @(
        "-JreDir", $JreDir,
        "-PythonDir", $PythonDir,
        "-VroomExe", $VroomExe,
        "-OsrmDir", $OsrmDir,
        "-OsrmDataDir", $OsrmDataDir,
        "-ReportPath", "artifacts/test-reports/windows-portable-release-gate/runtime-summary.json"
    )
}

Run-Stage "package-portable" {
    Invoke-Step (Join-Path $Root "scripts/package-windows-portable.ps1") @(
        "-JreDir", $JreDir,
        "-PythonDir", $PythonDir,
        "-VroomExe", $VroomExe,
        "-OsrmDir", $OsrmDir,
        "-OsrmDataDir", $OsrmDataDir
    )
    $bundle = Join-Path $Root $BundleRoot
    $zip = Join-Path $Root "build/release/irx-portable-windows-x64.zip"
    if (-not (Test-Path $bundle)) { throw "bundle missing: $bundle" }
    if (-not (Test-Path $zip)) { throw "zip missing: $zip" }
    $summary.artifacts.bundle = $bundle
    $summary.artifacts.zip = $zip
}

Run-Stage "portable-smoke" {
    $bundle = Join-Path $Root $BundleRoot
    if (-not $SkipSmokeStart) {
        $start = Join-Path $bundle "start-irx.bat"
        if (-not (Test-Path $start)) { throw "start script missing: $start" }
        Start-Process -FilePath $start -WorkingDirectory $bundle -WindowStyle Minimized | Out-Null
        Start-Sleep -Seconds 10
    }
    Invoke-Step (Join-Path $Root "scripts/smoke-windows-portable.ps1") @(
        "-BundleRoot", $bundle,
        "-BackendPort", $BackendPort,
        "-OsrmPort", $OsrmPort
    )
}

Run-Stage "baseline-vs-portable-compare" {
    Invoke-Step (Join-Path $Root "scripts/compare-package-baseline.ps1") @()
}

if (-not $SkipInstaller) {
    Run-Stage "installer-build" {
        Invoke-Step (Join-Path $Root "scripts/package-windows-installer.ps1") @()
    }
}

$summary.overallPass = ($summary.stages | Where-Object { $_.status -ne "PASS" }).Count -eq 0
$summary.completedAt = (Get-Date).ToString("o")
Save-Summary
Write-Host "SUMMARY=$SummaryPath"

if (-not $summary.overallPass) { exit 1 }
