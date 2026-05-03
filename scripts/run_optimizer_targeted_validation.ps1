param(
    [int]$CommandTimeoutSeconds = 300,
    [switch]$NoStopDaemon
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$gradle = Join-Path $repoRoot "gradlew.bat"

function Invoke-GradleStep {
    param(
        [string]$Name,
        [string[]]$Arguments
    )

    Write-Host "==> $Name"
    $startedAt = Get-Date
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "cmd.exe"
    $processInfo.Arguments = (@("/c", "`"$gradle`"") + $Arguments) -join " "
    $processInfo.WorkingDirectory = $repoRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $false
    $processInfo.RedirectStandardError = $false
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    [void]$process.Start()
    if (-not $process.WaitForExit($CommandTimeoutSeconds * 1000)) {
        try { $process.Kill($true) } catch { $process.Kill() }
        throw "Gradle step '$Name' timed out after ${CommandTimeoutSeconds}s"
    }
    $elapsed = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 2)
    if ($process.ExitCode -ne 0) {
        throw "Gradle step '$Name' failed with exit code $($process.ExitCode) after ${elapsed}s"
    }
    Write-Host "<== $Name passed in ${elapsed}s"
}

if (-not $NoStopDaemon) {
    Invoke-GradleStep -Name "Stop stale Gradle daemons" -Arguments @("--stop")
}

Invoke-GradleStep -Name "Compile test classes" -Arguments @("testClasses")

$testGroups = @(
    @("test", "--tests", "com.routechain.v2.repair.*", "--tests", "com.routechain.v2.selector.*"),
    @("test", "--tests", "com.routechain.v2.constraints.*", "--tests", "com.routechain.v2.optimizer.*", "--tests", "com.routechain.v2.active.*"),
    @("test", "--tests", "com.routechain.v2.rolling.*", "--tests", "com.routechain.v2.route.RouteProposalEngineTest"),
    @("test", "--tests", "com.routechain.v2.DispatchV2CoreSelectorSliceTest")
)

foreach ($arguments in $testGroups) {
    Invoke-GradleStep -Name ($arguments -join " ") -Arguments $arguments
}

Write-Host "Optimizer targeted validation passed. Recommended external timeout: ${CommandTimeoutSeconds}s or higher on cold Windows Gradle runs."
