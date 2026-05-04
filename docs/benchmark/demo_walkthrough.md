# Benchmark Demo Walkthrough

This walkthrough demonstrates the complete benchmark story: Phase 56F stable runner vs VROOM industry baseline, benchmark suite registry, synthetic food data, and final report.

## 1. Start the Industry Baseline

```powershell
docker compose -f docker/vroom/docker-compose.yml up -d
docker/vroom/healthcheck.ps1
```

If `GET /` returns `404`, continue. The health endpoint is `/health`, and optimization requests are submitted by POST.

## 2. Run the Unified Benchmark

```powershell
py -3.13 scripts/run_phase63_unified_benchmark_suite.py `
  --suite li-lim-8case `
  --champions vroom `
  --challenger phase56f `
  --vroom-url http://localhost:3000 `
  --time-limit 30s `
  --output-dir artifacts/final/li_lim_8case_v1
```

This command runs the Phase 56F stable certification challenger, runs the VROOM comparator, and generates VROOM gap analysis.

## 3. Generate Production-Like Synthetic Data

```powershell
py -3.13 scripts/generate_phase64_synthetic_food_dataset.py `
  --output-dir benchmarks/synthetic_food/generated_v1 `
  --seed 64
```

The generated scenarios provide production-like stress coverage without real customer data.

## 4. Build the Final Report

```powershell
py -3.13 scripts/run_phase65_final_system_evaluation_report.py `
  --input-dir artifacts/final/li_lim_8case_v1 `
  --output docs/benchmark/final_system_evaluation_report.md
```

Open `docs/benchmark/final_system_evaluation_report.md` and present the result as:

- Phase 56F is production-safe/stable for certification and shadow mode.
- VROOM is the industry comparator.
- IntelligentRouteX is currently industry-quality **partial**, because VROOM still wins quality on feasible cases.
- VROOM hard-fails/timeouts and Challenger hard-fails/overBudget are tracked separately.

## 5. Expected Honest Conclusion

The correct current conclusion avoids claiming full VROOM superiority. Use this wording:

> IntelligentRouteX has a production-safe, deterministic certification path and a complete industry-comparator benchmark system. It is safer and more stable in the current comparator, but quality remains partial because VROOM still wins feasible cases on distance or vehicle count.
