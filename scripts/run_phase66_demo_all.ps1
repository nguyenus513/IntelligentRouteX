param(
  [string]$Suite = "li-lim-8case",
  [string]$OutputDir = "artifacts/final/li_lim_8case_v1",
  [string]$VroomUrl = "http://localhost:3000",
  [string]$TimeLimit = "30s",
  [switch]$SkipDockerStart,
  [switch]$DryRunConversion
)

$ErrorActionPreference = "Stop"

Write-Host "[Phase 66] Benchmark demo starting"

if (-not $SkipDockerStart) {
  Write-Host "[Phase 66] Starting VROOM with docker compose"
  docker compose -f docker/vroom/docker-compose.yml up -d
}

Write-Host "[Phase 66] Checking VROOM health"
docker/vroom/healthcheck.ps1

Write-Host "[Phase 66] Running Phase 63 unified benchmark"
$phase63Args = @(
  "scripts/run_phase63_unified_benchmark_suite.py",
  "--suite", $Suite,
  "--champions", "vroom",
  "--challenger", "phase56f",
  "--vroom-url", $VroomUrl,
  "--time-limit", $TimeLimit,
  "--output-dir", $OutputDir
)
if ($DryRunConversion) {
  $phase63Args += "--dry-run-conversion"
}
py -3.13 @phase63Args

Write-Host "[Phase 66] Generating synthetic food dataset"
py -3.13 scripts/generate_phase64_synthetic_food_dataset.py `
  --output-dir benchmarks/synthetic_food/generated_v1 `
  --seed 64

Write-Host "[Phase 66] Building Phase 65 final report"
py -3.13 scripts/run_phase65_final_system_evaluation_report.py `
  --input-dir $OutputDir `
  --output docs/benchmark/final_system_evaluation_report.md

Write-Host "[Phase 66] Demo complete"
Write-Host "Report: docs/benchmark/final_system_evaluation_report.md"
