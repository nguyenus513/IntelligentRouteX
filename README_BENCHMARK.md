# IntelligentRouteX Benchmark Quickstart

This repository now packages IntelligentRouteX as a benchmarkable routing optimization system, not only a standalone solver.

## Roles

- **Stable system**: Phase 56F stable certification runner, `scripts/run_phase56b_stable_promoted_runner.py --stable-incumbent-replay`.
- **Industry baseline**: VROOM, launched from `docker/vroom/docker-compose.yml`.
- **Research baseline**: Phase 47 adaptive natural runner, retained for quality research but not strict certification.
- **Reports**: Phase 63 unified benchmark artifacts and Phase 65 final evaluation report.

## Start VROOM

```powershell
docker compose -f docker/vroom/docker-compose.yml up -d
docker/vroom/healthcheck.ps1
```

Use `/health` for readiness. `GET /` can return `404` and is not a service failure.

## Run Li-Lim 8-Case Benchmark

```powershell
py -3.13 scripts/run_phase63_unified_benchmark_suite.py `
  --suite li-lim-8case `
  --champions vroom `
  --challenger phase56f `
  --vroom-url http://localhost:3000 `
  --time-limit 30s `
  --output-dir artifacts/final/li_lim_8case_v1
```

## Run Synthetic Food Benchmark

```powershell
py -3.13 scripts/run_phase63_unified_benchmark_suite.py `
  --suite synthetic-food-smoke `
  --champions vroom `
  --challenger phase56f `
  --vroom-url http://localhost:3000 `
  --time-limit 30s `
  --output-dir artifacts/final/synthetic_food_smoke_v1
```

## Generate Synthetic Food Dataset

```powershell
py -3.13 scripts/generate_phase64_synthetic_food_dataset.py `
  --output-dir benchmarks/synthetic_food/generated_v1 `
  --seed 64
```

Scenarios include `lunch_peak`, `dinner_peak`, `apartment_cluster`, `rain_peak`, `sparse_suburban`, and `cancellation_risk`.

## Build Final Report

```powershell
py -3.13 scripts/run_phase65_final_system_evaluation_report.py `
  --input-dir artifacts/final/li_lim_8case_v1 `
  --output docs/benchmark/final_system_evaluation_report.md
```

For synthetic food reporting, point `--input-dir` at `artifacts/final/synthetic_food_smoke_v1` or `artifacts/final/synthetic_food_full_v1`.

## Result Interpretation

- **Production-safe** means hard violations are `0`, accepted objective regressions are absent, and `overBudget` is `0` under the certification runner.
- **Industry-quality partial** means VROOM still wins quality on feasible cases, usually distance or vehicle count, while IntelligentRouteX may be more stable when VROOM hard-fails or times out.
- **VROOM hard-fail/timeout** is tracked separately from adapter mapping, schema, import, and time-unit issues by Phase 58B diagnostics.
- **Do not claim VROOM superiority or IntelligentRouteX superiority from one metric only**; use Phase 59 gap classes and Phase 65 final verdict.

## Key Artifacts

- `artifacts/final/li_lim_8case_v1/aggregate_summary.json`
- `artifacts/final/li_lim_8case_v1/vroom_comparator/aggregate_summary.json`
- `artifacts/final/li_lim_8case_v1/vroom_gap_analyzer/phase59_vroom_gap_summary.json`
- `docs/benchmark/final_system_evaluation_report.md`
