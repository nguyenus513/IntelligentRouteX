param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$FastTimeoutSeconds = 220,
  [int]$QualityTimeoutSeconds = 420,
  [string]$OutputDir = "artifacts/test-reports/final-demo"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$root = Resolve-Path "$PSScriptRoot/.."
Push-Location $root
try {
  $env:GRADLE_USER_HOME = (Resolve-Path ".").Path + "\.gradle-tmp"
  .\gradlew.bat compileJava --no-daemon
  & "$PSScriptRoot/run-fast-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $FastTimeoutSeconds -OutputDir (Join-Path $OutputDir "fast")
  & "$PSScriptRoot/run-quality-benchmark-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $QualityTimeoutSeconds -OutputDir (Join-Path $OutputDir "quality")
  & "$PSScriptRoot/run-live-demo-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "live")

  $fast = Get-Content (Join-Path $OutputDir "fast/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $quality = Get-Content (Join-Path $OutputDir "quality/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $live = Get-Content (Join-Path $OutputDir "live/live-demo-gate-summary.json") -Raw | ConvertFrom-Json
  $summary = [pscustomobject]@{
    createdAt = (Get-Date).ToString("o")
    compileJava = "PASS"
    fastGatePassCount = $fast.passCount
    fastGateRuntimeMs = $fast.totalRuntimeMs
    qualityPassCount = $quality.passCount
    qualityRuntimeMs = $quality.totalRuntimeMs
    liveGatePass = $live.pass
    fastGateSummary = "fast/clean-cache-gate-summary.json"
    qualitySummary = "quality/clean-cache-gate-summary.json"
    liveSummary = "live/live-demo-gate-summary.json"
  }
  $summaryPath = Join-Path $OutputDir "final-demo-gate-summary.json"
  $summary | ConvertTo-Json -Depth 20 | Set-Content $summaryPath
  $summary
  Write-Output "SUMMARY=$summaryPath"
}
finally {
  Pop-Location
}
