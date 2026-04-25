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

`ortools-baseline` runs Python OR-Tools Routing as an independent baseline. `our-dispatch-v2` is still the deterministic normalized baseline path until `ExternalBenchmarkToDispatchCaseAdapter` is wired into the real Dispatch V2 runtime.

## Commands

```bash
python scripts/download_external_benchmarks.py --allow-mirror
python scripts/run_external_benchmark_certification.py --suite li-lim --preset preset:smoke --solver ortools-baseline --data-source official --mode benchmark-native --time-limit 75s
python scripts/run_external_benchmark_certification.py --suite solomon --preset preset:smoke --solver ortools-baseline --data-source official --mode benchmark-native --time-limit 75s
```

For current Dispatch V2 adapter readiness checks:

```bash
python scripts/run_external_benchmark_certification.py --suite li-lim --preset preset:smoke --solver our-dispatch-v2 --data-source official --mode benchmark-native --time-limit 30s
python scripts/run_external_benchmark_certification.py --suite solomon --preset preset:smoke --solver our-dispatch-v2 --data-source official --mode benchmark-native --time-limit 30s
```
