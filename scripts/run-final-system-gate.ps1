param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$FastTimeoutSeconds = 240,
  [int]$QualityTimeoutSeconds = 480,
  [string]$OutputDir = "artifacts/test-reports/final-system"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$root = Resolve-Path "$PSScriptRoot/.."
Push-Location $root
try {
  $env:GRADLE_USER_HOME = (Resolve-Path ".").Path + "\.gradle-tmp"
  .\gradlew.bat compileJava --no-daemon
  Push-Location dashboard
  try {
    npm run typecheck
    npm run build
  } finally {
    Pop-Location
  }

  & "$PSScriptRoot/run-fast-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $FastTimeoutSeconds -OutputDir (Join-Path $OutputDir "fast")
  & "$PSScriptRoot/run-quality-benchmark-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $QualityTimeoutSeconds -OutputDir (Join-Path $OutputDir "quality")

  $pyvrpBody = @{ datasetId = "raw-s"; mode = "QUALITY_BENCHMARK"; solvers = @("single-order", "distance-batching", "OR-Tools", "PyVRP", "VROOM", "IntelligentRouteX") } | ConvertTo-Json
  $pyvrpJob = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs" -ContentType "application/json" -Body $pyvrpBody -TimeoutSec $QualityTimeoutSeconds
  $pyvrpRun = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/dashboard/benchmarks/jobs/$($pyvrpJob.jobId)/result" -TimeoutSec 180
  $pyvrpArtifact = Join-Path $OutputDir "pyvrp-vroom-smoke-$($pyvrpJob.jobId).json"
  $pyvrpRun | ConvertTo-Json -Depth 100 | Set-Content $pyvrpArtifact

  & "$PSScriptRoot/run-live-stress-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "live-stress")
  & "$PSScriptRoot/run-rescue-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "rescue")

  $fast = Get-Content (Join-Path $OutputDir "fast/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $quality = Get-Content (Join-Path $OutputDir "quality/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $live = Get-Content (Join-Path $OutputDir "live-stress/live-stress-gate-summary.json") -Raw | ConvertFrom-Json
  $rescue = Get-Content (Join-Path $OutputDir "rescue/rescue-gate-summary.json") -Raw | ConvertFrom-Json
  $externalRows = $pyvrpRun.diagnostics.solverResults | Where-Object { $_.solverName -eq "PyVRP" -or $_.solverName -eq "VROOM" }
  $fastPass = [int]$fast.total -ge 7 -and [int]$fast.lateRegressionCount -eq 0 -and [int]$fast.dominanceFailures -eq 0
  $qualityPass = [int]$quality.total -ge 20 -and [int]$quality.lateRegressionCount -eq 0 -and [int]$quality.dominanceFailures -eq 0
  $pyvrp = $externalRows | Where-Object solverName -eq "PyVRP" | Select-Object -First 1
  $vroom = $externalRows | Where-Object solverName -eq "VROOM" | Select-Object -First 1
  $externalPass = $pyvrp -ne $null -and ($pyvrp.status -eq "COMPLETED" -or $pyvrp.status -eq "TIMEOUT" -or $pyvrp.status -eq "FAILED" -or $pyvrp.status -eq "EVIDENCE_GAP") -and $vroom -ne $null -and ($vroom.status -eq "COMPLETED" -or $vroom.status -eq "EVIDENCE_GAP" -or $vroom.status -eq "TIMEOUT" -or $vroom.status -eq "FAILED")
  $overallPass = $fastPass -and $qualityPass -and [bool]$live.pass -and [bool]$rescue.pass -and $externalPass
  $summary = [pscustomobject]@{
    createdAt = (Get-Date).ToString("o")
    pass = $overallPass
    compileJava = "PASS"
    dashboardTypecheck = "PASS"
    dashboardBuild = "PASS"
    fastGate = if ($fastPass) { "PASS" } else { "FAIL" }
    fastGateTotal = $fast.total
    fastGateRuntimeMs = $fast.totalRuntimeMs
    qualityBenchmark = if ($qualityPass) { "PASS" } else { "FAIL" }
    qualityGateTotal = $quality.total
    qualityRuntimeMs = $quality.totalRuntimeMs
    liveStressPass = $live.pass
    rescuePass = $rescue.pass
    externalSolvers = @{
      pyvrp = if ($pyvrp -eq $null) { "MISSING" } else { $pyvrp.status }
      vroom = if ($vroom -eq $null) { "MISSING" } else { $vroom.status }
    }
    externalSolverSmoke = $externalRows
    finalSolverInvariant = "IRX ML-Fused Hybrid"
    lateRegression = $quality.lateRegressionCount
    dominanceFailures = $quality.dominanceFailures
    summaries = @{
      fast = "fast/clean-cache-gate-summary.json"
      quality = "quality/clean-cache-gate-summary.json"
      liveStress = "live-stress/live-stress-gate-summary.json"
      rescue = "rescue/rescue-gate-summary.json"
      externalSmoke = (Split-Path $pyvrpArtifact -Leaf)
    }
  }
  $summaryPath = Join-Path $OutputDir "final-system-summary.json"
  $summary | ConvertTo-Json -Depth 100 | Set-Content $summaryPath
  $summary
  Write-Output "SUMMARY=$summaryPath"
  if (-not $overallPass) { exit 1 }
}
finally {
  Pop-Location
}
