param(
    [switch]$SkipAndroid
)

$ErrorActionPreference = "Stop"

function Run-Step($Name, [scriptblock]$Command) {
    Write-Host "--- $Name ---"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Run-Step "Backend dispatch controller test" {
    .\gradlew.bat test --tests com.routechain.api.DispatchV2ControllerTest --no-daemon
}

Run-Step "Functions install" {
    Push-Location functions
    npm ci
    Pop-Location
}

Run-Step "Functions TypeScript build" {
    Push-Location functions
    npm run build
    Pop-Location
}

Run-Step "Functions audit" {
    Push-Location functions
    npm audit --audit-level=moderate
    Pop-Location
}

if (-not $SkipAndroid) {
    $localSdk = Join-Path $repoRoot ".android-sdk"
    if (Test-Path $localSdk) {
        $env:ANDROID_HOME = (Resolve-Path $localSdk).Path
        $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    }

    Run-Step "Android debug build" {
        Push-Location android\routefood-app
        .\gradlew.bat :app:assembleDebug --no-daemon
        Pop-Location
    }
}

Write-Host "Diagnostics completed successfully."
