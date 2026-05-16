param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$DatasetTimeoutSeconds = 220,
  [string]$OutputDir = "artifacts/test-reports"
)

$ErrorActionPreference = "Stop"
& "$PSScriptRoot/run-clean-cache-gate.ps1" `
  -BaseUrl $BaseUrl `
  -Mode "FAST_GATE" `
  -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
  -OutputDir $OutputDir
