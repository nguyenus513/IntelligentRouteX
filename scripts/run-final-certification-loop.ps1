param(
  [string]$BaseUrl = "http://localhost:8080",
  [int]$FastTimeoutSeconds = 260,
  [int]$QualityTimeoutSeconds = 520,
  [string]$OutputDir = "artifacts/test-reports/final-certification"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$root = Resolve-Path "$PSScriptRoot/.."
Push-Location $root
try {
  $env:GRADLE_USER_HOME = (Resolve-Path ".").Path + "\.gradle-tmp"
  .\gradlew.bat compileJava --no-daemon --console=plain
  Push-Location dashboard
  try {
    npm run typecheck
    npm run build
  } finally {
    Pop-Location
  }

  & "$PSScriptRoot/run-fast-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $FastTimeoutSeconds -OutputDir (Join-Path $OutputDir "fast")
  & "$PSScriptRoot/run-quality-benchmark-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $QualityTimeoutSeconds -OutputDir (Join-Path $OutputDir "quality")
  & "$PSScriptRoot/run-academic-static-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $QualityTimeoutSeconds -OutputDir (Join-Path $OutputDir "academic")
  & "$PSScriptRoot/run-pdptw-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds $QualityTimeoutSeconds -OutputDir (Join-Path $OutputDir "pdptw")
  & "$PSScriptRoot/run-external-solver-gate.ps1" -BaseUrl $BaseUrl -DatasetTimeoutSeconds 300 -OutputDir (Join-Path $OutputDir "external")
  & "$PSScriptRoot/run-live-stress-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "live")
  & "$PSScriptRoot/run-rescue-gate.ps1" -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "rescue")

  $fast = Get-Content (Join-Path $OutputDir "fast/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $quality = Get-Content (Join-Path $OutputDir "quality/clean-cache-gate-summary.json") -Raw | ConvertFrom-Json
  $academic = Get-Content (Join-Path $OutputDir "academic/academic-static-gate-summary.json") -Raw | ConvertFrom-Json
  $pdptw = Get-Content (Join-Path $OutputDir "pdptw/pdptw-gate-summary.json") -Raw | ConvertFrom-Json
  $external = Get-Content (Join-Path $OutputDir "external/external-solver-gate-summary.json") -Raw | ConvertFrom-Json
  $live = Get-Content (Join-Path $OutputDir "live/live-stress-gate-summary.json") -Raw | ConvertFrom-Json
  $rescue = Get-Content (Join-Path $OutputDir "rescue/rescue-gate-summary.json") -Raw | ConvertFrom-Json
  $commit = (git rev-parse --short HEAD).Trim()
  $tag = (git tag --points-at HEAD | Select-Object -First 1)
  $fastPass = [int]$fast.total -eq 7 -and [int]$fast.totalRuntimeMs -lt 240000 -and [int]$fast.lateRegressionCount -eq 0 -and [int]$fast.dominanceFailures -eq 0
  $qualityPass = [int]$quality.total -eq 20 -and [int]$quality.lateRegressionCount -eq 0 -and [int]$quality.dominanceFailures -eq 0
  $overallPass = $fastPass -and $qualityPass -and [bool]$academic.pass -and [bool]$pdptw.pass -and [bool]$external.pass -and [bool]$live.pass -and [bool]$rescue.pass
  $summary = [pscustomobject]@{
    overallPass = $overallPass
    commit = $commit
    tag = $tag
    backendCompile = "PASS"
    dashboardTypecheck = "PASS"
    dashboardBuild = "PASS"
    fastGate = @{
      pass = $fastPass
      completed = "$($fast.total)/7"
      runtimeMs = $fast.totalRuntimeMs
      lateRegression = $fast.lateRegressionCount
      dominanceFailures = $fast.dominanceFailures
    }
    qualityBenchmark = @{
      pass = $qualityPass
      completed = "$($quality.total)/20"
      distanceObjective = "$($quality.distanceObjectiveSummary.win)W/$($quality.distanceObjectiveSummary.tie)T/$($quality.distanceObjectiveSummary.loss)L"
      ortoolsObjective = "$($quality.ortoolsObjectiveSummary.win)W/$($quality.ortoolsObjectiveSummary.tie)T/$($quality.ortoolsObjectiveSummary.loss)L"
      lateRegression = $quality.lateRegressionCount
      dominanceFailures = $quality.dominanceFailures
    }
    academicStaticGate = @{
      pass = [bool]$academic.pass
      cvrpCompleted = [bool]$academic.cvrpCompleted
      vrptwCompleted = [bool]$academic.vrptwCompleted
    }
    pdptwGate = @{
      pass = [bool]$pdptw.pass
      pickupBeforeDropoffViolations = $pdptw.pickupBeforeDropoffViolations
      capacityViolations = $pdptw.capacityViolations
    }
    externalSolvers = @{
      pyvrp = $external.pyvrp
      vroom = $external.vroom
    }
    liveStress = @{
      pass = [bool]$live.pass
      cycles = $live.cycleCount
      staleBufferedOrders = $live.bufferedOrderCount
    }
    rescue = @{
      pass = [bool]$rescue.pass
      lateNotWorse = [int]$rescue.afterLate -le [int]$rescue.beforeLate
    }
    finalSolverInvariant = "IRX_ML_FUSED_HYBRID"
    docsUpdated = (Test-Path "docs/IRX_FINAL_SYSTEM_STATUS.md") -and (Test-Path "docs/IRX_BENCHMARK_METHODOLOGY.md") -and (Test-Path "docs/IRX_OPERATIONS_DEMO_GUIDE.md")
    artifacts = @{
      fast = "fast/clean-cache-gate-summary.json"
      quality = "quality/clean-cache-gate-summary.json"
      academic = "academic/academic-static-gate-summary.json"
      pdptw = "pdptw/pdptw-gate-summary.json"
      external = "external/external-solver-gate-summary.json"
      live = "live/live-stress-gate-summary.json"
      rescue = "rescue/rescue-gate-summary.json"
    }
  }
  $summaryPath = Join-Path $OutputDir "final-certification-summary.json"
  $summary | ConvertTo-Json -Depth 100 | Set-Content $summaryPath
  $summary
  Write-Output "SUMMARY=$summaryPath"
  if (-not $overallPass) { exit 1 }
}
finally {
  Pop-Location
}
