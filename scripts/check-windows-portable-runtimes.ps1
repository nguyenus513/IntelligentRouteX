param(
    [string]$JreDir = $env:IRX_PORTABLE_JRE_DIR,
    [string]$PythonDir = $env:IRX_PORTABLE_PYTHON_DIR,
    [string]$VroomExe = $env:IRX_PORTABLE_VROOM_EXE,
    [string]$OsrmDir = $env:IRX_PORTABLE_OSRM_DIR,
    [string]$OsrmDataDir = $env:IRX_PORTABLE_OSRM_DATA_DIR,
    [string]$ReportPath = "artifacts/test-reports/windows-portable-runtime-check/summary.json"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReportFullPath = Join-Path $Root $ReportPath

function Test-RequiredPath($Path, $Code, $Name) {
    $ok = -not [string]::IsNullOrWhiteSpace($Path) -and (Test-Path $Path)
    return [ordered]@{ name = $Name; code = $Code; path = $Path; ok = $ok }
}

function Invoke-Tool($Name, $Command, $Arguments) {
    if ([string]::IsNullOrWhiteSpace($Command)) {
        return [ordered]@{ name = $Name; ok = $false; command = $Command; error = "missing" }
    }
    if (-not (Test-Path $Command)) {
        return [ordered]@{ name = $Name; ok = $false; command = $Command; error = "missing" }
    }
    try {
        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $Command
        $psi.Arguments = ($Arguments | ForEach-Object {
            $argument = $_.ToString()
            if ($argument -match '[\s"]') { '"' + ($argument -replace '"', '\"') + '"' } else { $argument }
        }) -join " "
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $process = [System.Diagnostics.Process]::Start($psi)
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return [ordered]@{ name = $Name; ok = ($process.ExitCode -eq 0); exitCode = $process.ExitCode; command = $Command; output = (($stdout + "`n" + $stderr).Trim()) }
    } catch {
        return [ordered]@{ name = $Name; ok = $false; command = $Command; error = $_.Exception.Message; output = "" }
    }
}

$javaExe = if ($JreDir) { Join-Path $JreDir "bin/java.exe" } else { $null }
$pythonExe = if ($PythonDir) { Join-Path $PythonDir "python.exe" } else { $null }
$osrmRouted = if ($OsrmDir) { Join-Path $OsrmDir "osrm-routed.exe" } else { $null }
$osrmMap = $null
if ($OsrmDataDir -and (Test-Path $OsrmDataDir)) {
    $osrmMap = Get-ChildItem $OsrmDataDir -Filter "*.osrm*" -ErrorAction SilentlyContinue | Select-Object -First 1
}

$summary = [ordered]@{
    schemaVersion = "irx-windows-portable-runtime-check/v1"
    startedAt = (Get-Date).ToString("o")
    root = $Root.Path
    inputs = [ordered]@{
        jreDir = $JreDir
        pythonDir = $PythonDir
        vroomExe = $VroomExe
        osrmDir = $OsrmDir
        osrmDataDir = $OsrmDataDir
    }
    requiredPaths = @(
        (Test-RequiredPath $JreDir "JRE_DIR" "JRE directory"),
        (Test-RequiredPath $javaExe "JAVA_EXE" "Java executable"),
        (Test-RequiredPath $PythonDir "PYTHON_DIR" "Python directory"),
        (Test-RequiredPath $pythonExe "PYTHON_EXE" "Python executable"),
        (Test-RequiredPath $VroomExe "VROOM_EXE" "VROOM executable"),
        (Test-RequiredPath $OsrmDir "OSRM_DIR" "OSRM directory"),
        (Test-RequiredPath $osrmRouted "OSRM_ROUTED_EXE" "OSRM routed executable"),
        (Test-RequiredPath $OsrmDataDir "OSRM_DATA_DIR" "OSRM data directory"),
        [ordered]@{ name = "OSRM .osrm map data"; code = "OSRM_MAP"; path = if ($osrmMap) { $osrmMap.FullName } else { $null }; ok = ($null -ne $osrmMap) }
    )
    toolChecks = @()
}

$summary.toolChecks += Invoke-Tool "javaVersion" $javaExe @("-version")
$summary.toolChecks += Invoke-Tool "pythonVersion" $pythonExe @("--version")
$summary.toolChecks += Invoke-Tool "pyvrpImport" $pythonExe @("-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'pyvrp-ok'))")
$summary.toolChecks += Invoke-Tool "vroomVersion" $VroomExe @("--version")
$summary.toolChecks += Invoke-Tool "osrmVersion" $osrmRouted @("--version")

$summary.overallPass = ($summary.requiredPaths | Where-Object { -not $_.ok }).Count -eq 0 -and ($summary.toolChecks | Where-Object { -not $_.ok }).Count -eq 0
$summary.completedAt = (Get-Date).ToString("o")

New-Item -ItemType Directory -Force -Path (Split-Path $ReportFullPath -Parent) | Out-Null
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $ReportFullPath
Write-Host "SUMMARY=$ReportFullPath"

if (-not $summary.overallPass) {
    $missing = ($summary.requiredPaths | Where-Object { -not $_.ok } | ForEach-Object { $_.code }) -join ","
    $failed = ($summary.toolChecks | Where-Object { -not $_.ok } | ForEach-Object { $_.name }) -join ","
    throw "WINDOWS_PORTABLE_RUNTIME_CHECK_FAILED missing=[$missing] failed=[$failed]"
}
