# Dispatch V2 External Benchmark Certification

This rail evaluates Dispatch V2 against academic benchmark instances without OSRM, TomTom, weather, or HCM road-native assumptions. Academic benchmark mode uses the distance/time convention provided by the instance so objective gaps can be compared against best-known solutions.

## Modes

- `benchmark-native`: uses instance coordinates and benchmark-native distance matrices only.
- `realistic-food-delivery`: out of scope for this rail; use the HCM road-native benchmark separately.

## Suites

- Solomon VRPTW validates vehicle routing with time windows.
- Li & Lim PDPTW validates pickup/dropoff precedence, capacity, and time windows.
- CVRPLIB/VRP-REP are placeholders until their parser and fixture policy are enabled.

## Verdicts

- `PASS`: feasible, no constraint violations, objective gap within threshold, runtime within limit.
- `PASS_WITH_LIMITS`: feasible but distance gap is high, best-known solution is missing, or vehicle count is above best-known while the route remains feasible.
- `FAIL`: infeasible, timeout, capacity violation, time-window violation, vehicle-count violation, or pickup/dropoff violation.
- `EVIDENCE_GAP`: parser, fixture, benchmark data, or optional baseline is unavailable.

## Current Scope

The rail now supports fixture smoke data and official-format smoke data. Direct SINTEF asset downloads can be blocked by browser challenges in terminal environments, so `scripts/download_external_benchmarks.py --allow-mirror` records the primary SINTEF URL and the raw mirror actually used in `benchmarks/external/official/download_manifest.json`.

`ortools-baseline` runs Python OR-Tools Routing as an independent baseline. `our-dispatch-v2` now runs through `ExternalBenchmarkToDispatchCaseAdapter` in benchmark-native mode, preserving benchmark matrix, capacity, time-window, and pickup/dropoff constraints that the current food-delivery Java domain cannot represent losslessly yet.

## Commands

```bash
python scripts/download_external_benchmarks.py --allow-mirror
python scripts/run_external_benchmark_certification.py --suite li-lim --preset preset:smoke --solver ortools-baseline --data-source official --mode benchmark-native --time-limit 75s
python scripts/run_external_benchmark_certification.py --suite solomon --preset preset:smoke --solver ortools-baseline --data-source official --mode benchmark-native --time-limit 75s
```

For Dispatch V2 external benchmark adapter checks:

```bash
python scripts/run_external_benchmark_certification.py --suite li-lim --preset preset:smoke --solver our-dispatch-v2 --data-source official --mode benchmark-native --time-limit 30s
python scripts/run_external_benchmark_certification.py --suite solomon --preset preset:smoke --solver our-dispatch-v2 --data-source official --mode benchmark-native --time-limit 30s
```
## Current Smoke Result

With official-format smoke data and `75s` per instance, `our-dispatch-v2` via `external-benchmark-dispatch-adapter-v1` is feasible on all 6 smoke instances:

- Solomon `C101`: `PASS`.
- Solomon `R101`, `RC101`: `PASS_WITH_LIMITS` because vehicle count is above best-known.
- Li-Lim `LC101`: `PASS`.
- Li-Lim `LR101`, `LRC101`: `PASS_WITH_LIMITS` because vehicle count is above best-known.

This certifies feasibility for the external adapter path, not full academic optimality and not the Java 12-stage food-delivery runtime.
