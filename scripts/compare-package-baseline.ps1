param(
    [string]$BaselineSummary = "artifacts/test-reports/package-baseline/current-summary.json",
    [string]$PortableSummary = "build/release/windows-portable/irx-portable-windows-x64/data/logs/smoke/smoke-summary.json",
    [string]$OutputDir = "artifacts/test-reports/package-compare"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BaselinePath = Join-Path $Root $BaselineSummary
$PortablePath = Join-Path $Root $PortableSummary
$OutputPath = Join-Path $Root $OutputDir
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

if (-not (Test-Path $BaselinePath)) { throw "Missing baseline summary: $BaselinePath" }
if (-not (Test-Path $PortablePath)) { throw "Missing portable summary: $PortablePath" }

$baseline = Get-Content $BaselinePath -Raw | ConvertFrom-Json
$portable = Get-Content $PortablePath -Raw | ConvertFrom-Json
$required = @("file-app/irx-backend.jar", "file-app/public/index.html", "file-runtime/jre/bin/java.exe", "file-runtime/python/python.exe", "file-runtime/vroom/vroom.exe", "file-runtime/osrm/osrm-routed.exe", "pyvrpImport", "osrmRoute", "backendReady", "frontend", "compareJob", "compareResult", "bigdataIngest", "bigdataRuntime")
$missing = @()
foreach ($name in $required) {
    $check = $portable.checks.$name
    if (-not $check -or $check.status -ne "PASS") { $missing += $name }
}
$overallPass = ($baseline.overallPass -eq $true) -and ($portable.overallPass -eq $true) -and ($missing.Count -eq 0)
$summary = [ordered]@{
    schemaVersion = "irx-package-compare/v1"
    generatedAt = (Get-Date).ToString("o")
    overallPass = $overallPass
    baselinePass = $baseline.overallPass
    portablePass = $portable.overallPass
    missingPortableChecks = $missing
    baselineSummary = $BaselinePath
    portableSummary = $PortablePath
}
$jsonPath = Join-Path $OutputPath "summary.json"
$mdPath = Join-Path $OutputPath "report.md"
$summary | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $jsonPath
@"
# IRX Package Comparison

- Overall: **$overallPass**
- Baseline pass: $($baseline.overallPass)
- Portable pass: $($portable.overallPass)
- Missing portable checks: $($missing -join ', ')

## Required Checks

$($required | ForEach-Object { $name = $_; "- ${name}: " + ($(if ($portable.checks.$name.status) { $portable.checks.$name.status } else { 'MISSING' })) } | Out-String)
"@ | Set-Content -Encoding UTF8 $mdPath
Write-Host "SUMMARY=$jsonPath"
if (-not $overallPass) { exit 1 }
