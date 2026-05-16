param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$DatasetTimeoutSeconds = 300,
  [string]$OutputDir = "artifacts/test-reports/final-certification/external"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$body = @{ datasetId = "raw-s"; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $body -TimeoutSec $DatasetTimeoutSeconds
$run = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($job.jobId)/result" -TimeoutSec 180
$artifact = Join-Path $OutputDir "external-solver-gate-$($job.jobId).json"
$run | ConvertTo-Json -Depth 100 | Set-Content $artifact

$pyvrp = $run.diagnostics.solverResults | Where-Object solverName -eq "PyVRP" | Select-Object -First 1
$vroom = $run.diagnostics.solverResults | Where-Object solverName -eq "VROOM" | Select-Object -First 1
$hybrid = $run.diagnostics.solverResults | Where-Object solverName -eq "IRX ML-Fused Hybrid" | Select-Object -First 1
$pyvrpHandled = $null -ne $pyvrp -and @("COMPLETED", "TIMEOUT", "FAILED", "EVIDENCE_GAP") -contains $pyvrp.status
$vroomHandled = $null -ne $vroom -and @("COMPLETED", "TIMEOUT", "FAILED", "EVIDENCE_GAP") -contains $vroom.status
$finalInvariant = $null -ne $hybrid -and $hybrid.status -eq "COMPLETED"
$pass = $pyvrpHandled -and $vroomHandled -and $finalInvariant
$gate = [pscustomobject]@{
  createdAt = (Get-Date).ToString("o")
  pass = $pass
  pyvrp = if ($null -eq $pyvrp) { "MISSING" } else { $pyvrp.status }
  vroom = if ($null -eq $vroom) { "MISSING" } else { $vroom.status }
  pyvrpReason = if ($null -eq $pyvrp) { "" } else { $pyvrp.reason }
  vroomReason = if ($null -eq $vroom) { "" } else { $vroom.reason }
  finalSolverInvariant = if ($finalInvariant) { "IRX_ML_FUSED_HYBRID" } else { "FAIL" }
  externalSeedContributors = $run.diagnostics.externalSeedContributors
  artifact = $artifact
}
$summaryPath = Join-Path $OutputDir "external-solver-gate-summary.json"
$gate | ConvertTo-Json -Depth 80 | Set-Content $summaryPath
$gate
Write-Output "SUMMARY=$summaryPath"
if (-not $pass) { exit 1 }
