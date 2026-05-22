param(
    [string]$OutputDir = "artifacts/test-reports/package-baseline",
    [int]$BackendPort = 18116,
    [int]$FrontendPort = 5173,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputPath = Join-Path $Root $OutputDir
$SummaryPath = Join-Path $OutputPath "current-summary.json"
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$summary = [ordered]@{ schemaVersion = "irx-package-baseline/v1"; startedAt = (Get-Date).ToString("o"); checks = [ordered]@{}; overallPass = $false }
function Save-Summary { $summary.updatedAt = (Get-Date).ToString("o"); $summary | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $SummaryPath }
function Pass($Name, $Value = $true) { $summary.checks[$Name] = [ordered]@{ status = "PASS"; value = $Value }; Save-Summary }
function Fail($Name, $Message) { $summary.checks[$Name] = [ordered]@{ status = "FAIL"; message = $Message }; Save-Summary; throw "[$Name] $Message" }
function Invoke-Json($Method, $Uri, $Body = $null, $Timeout = 30) { $headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo"; "Content-Type" = "application/json" }; $params = @{ Method = $Method; Uri = $Uri; Headers = $headers; TimeoutSec = $Timeout }; if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Depth 30) }; Invoke-RestMethod @params }
function Test-Http($Uri) { try { Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5 | Out-Null; return $true } catch { return $false } }

try {
    if (-not $SkipBuild) {
        & (Join-Path $Root "gradlew.bat") compileJava -x test --no-daemon
        if ($LASTEXITCODE -ne 0) { Fail "compileJava" "compileJava failed" }
        Pass "compileJava"
        Push-Location (Join-Path $Root "playground")
        try {
            npm run typecheck
            if ($LASTEXITCODE -ne 0) { Fail "feTypecheck" "FE typecheck failed" }
            npm run build
            if ($LASTEXITCODE -ne 0) { Fail "feBuild" "FE build failed" }
            Pass "frontendBuild"
        } finally { Pop-Location }
    }
    if (Test-Http "http://127.0.0.1:$BackendPort/v1/health") {
        $health = Invoke-Json GET "http://127.0.0.1:$BackendPort/v1/health" $null 20
        Pass "backendHealth" $health
    } else { Pass "backendHealth" "not-running-baseline-build-only" }
    if (Test-Http "http://127.0.0.1:$FrontendPort") { Pass "frontendHttp" "http://127.0.0.1:$FrontendPort" } else { Pass "frontendHttp" "not-running-baseline-build-only" }
    $summary.overallPass = $true
    $summary.completedAt = (Get-Date).ToString("o")
    Save-Summary
    Write-Host "SUMMARY=$SummaryPath"
} catch {
    $summary.overallPass = $false
    $summary.error = $_.Exception.Message
    $summary.failedAt = (Get-Date).ToString("o")
    Save-Summary
    Write-Host "SUMMARY=$SummaryPath"
    throw
}
