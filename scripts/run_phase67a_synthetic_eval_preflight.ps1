param(
  [int]$Seed = 64,
  [string]$VroomUrl = "http://localhost:3000",
  [string]$TimeLimit = "30s",
  [string]$RunId = "",
  [switch]$SkipDockerStart,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RunId)) {
  $RunId = Get-Date -Format "yyyyMMdd_HHmmss"
}

$SmokeOutputDir = "artifacts/final/synthetic_food_smoke_real_$RunId"
$FullOutputDir = "artifacts/final/synthetic_food_full_real_$RunId"
$FinalReport = "docs/benchmark/final_synthetic_food_evaluation_report.md"

function Assert-FreshOutputDir([string]$Path) {
  if ((Test-Path $Path) -and (-not $Force)) {
    throw "Output dir already exists: $Path. Use -Force or a new -RunId to avoid stale incumbent-cache."
  }
  if ((Test-Path $Path) -and $Force) {
    Remove-Item -LiteralPath $Path -Recurse -Force
  }
}

function Warn-IfVroomUnavailable([string]$SummaryPath) {
  if (-not (Test-Path $SummaryPath)) {
    return
  }
  $summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
  $counts = $summary.gapClassifications
  if ($null -ne $counts -and $null -ne $counts.'vroom-unavailable' -and [int]$counts.'vroom-unavailable' -gt 0) {
    Write-Warning "VROOM unavailable classifications detected in $SummaryPath"
  }
}

Write-Host "[Phase 67A] Synthetic evaluation preflight"
Write-Host "[Phase 67A] RunId: $RunId"

Assert-FreshOutputDir $SmokeOutputDir
Assert-FreshOutputDir $FullOutputDir

Write-Host "[Phase 67A] Regenerating synthetic food dataset"
py -3.13 scripts/generate_phase64_synthetic_food_dataset.py `
  --output-dir benchmarks/synthetic_food/generated_v1 `
  --seed $Seed

if (-not $SkipDockerStart) {
  Write-Host "[Phase 67A] Starting VROOM docker compose"
  docker compose -f docker/vroom/docker-compose.yml up -d
}

Write-Host "[Phase 67A] Checking VROOM health"
try {
  docker/vroom/healthcheck.ps1
} catch {
  Write-Warning "VROOM /health check failed. Continuing to real POST benchmark; GET / may return 404 and is not a failure."
}

Write-Host "[Phase 67A] Running synthetic-food-smoke real VROOM benchmark"
py -3.13 scripts/run_phase63_unified_benchmark_suite.py `
  --suite synthetic-food-smoke `
  --champions vroom `
  --challenger phase56f `
  --vroom-url $VroomUrl `
  --time-limit $TimeLimit `
  --output-dir $SmokeOutputDir

Warn-IfVroomUnavailable "$SmokeOutputDir/aggregate_summary.json"

Write-Host "[Phase 67A] Running synthetic-food-full real VROOM benchmark"
py -3.13 scripts/run_phase63_unified_benchmark_suite.py `
  --suite synthetic-food-full `
  --champions vroom `
  --challenger phase56f `
  --vroom-url $VroomUrl `
  --time-limit $TimeLimit `
  --output-dir $FullOutputDir

Warn-IfVroomUnavailable "$FullOutputDir/aggregate_summary.json"

Write-Host "[Phase 67A] Building final synthetic food report"
py -3.13 scripts/run_phase65_final_system_evaluation_report.py `
  --input-dir $FullOutputDir `
  --output $FinalReport

Write-Host "[Phase 67A] Complete"
Write-Host "Smoke summary: $SmokeOutputDir/aggregate_summary.md"
Write-Host "Full summary: $FullOutputDir/aggregate_summary.md"
Write-Host "VROOM gap summary: $FullOutputDir/vroom_gap_analyzer/phase59_vroom_gap_summary.md"
Write-Host "Final report: $FinalReport"
