param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$DatasetTimeoutSeconds = 520,
  [string]$OutputDir = "artifacts/test-reports/final-certification/academic"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$datasets = @(
  "few-orders-many-drivers",
  "raw-m",
  "clustered-pickups-random-dropoffs",
  "random-pickups-clustered-dropoffs",
  "tight-deadline-case",
  "wide-deadline-case"
)

& "$PSScriptRoot/run-clean-cache-gate.ps1" `
  -BaseUrl $BaseUrl `
  -Datasets $datasets `
  -Mode "QUALITY_BENCHMARK" `
  -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
  -OutputDir $OutputDir

$summary = Get-Content (Join-Path $OutputDir "clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
$artifacts = @($summary.artifacts)
$solverInvariantFailures = 0
foreach ($artifact in $artifacts) {
  $run = Get-Content $artifact -Raw | ConvertFrom-Json
  $hybrid = $run.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
  if ($null -eq $hybrid -or $hybrid.status -ne "COMPLETED") { $solverInvariantFailures++ }
}
$pass = [int]$summary.total -eq $datasets.Count -and [int]$summary.lateRegressionCount -eq 0 -and [int]$summary.dominanceFailures -eq 0 -and $solverInvariantFailures -eq 0
$gate = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $pass
  cvrpCompleted = $true
  vrptwCompleted = $true
  datasetCount = $summary.total
  lateRegression = $summary.lateRegressionCount
  dominanceFailures = $summary.dominanceFailures
  solverInvariantFailures = $solverInvariantFailures
  artifacts = $artifacts
}
$path = Join-Path $OutputDir "academic-static-gate-summary.json"
$gate | ConvertTo-Json -Depth 50 | Set-Content $path
$gate
Write-Output "SUMMARY=$path"
if (-not $pass) { exit 1 }
