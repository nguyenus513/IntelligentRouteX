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
- `PASS_WITH_LIMITS`: feasible but gap is high, or best-known solution is missing.
- `FAIL`: infeasible, timeout, capacity violation, time-window violation, or pickup/dropoff violation.
- `EVIDENCE_GAP`: parser, fixture, best-known data, or optional baseline is unavailable.

## Current Scope

The initial rail uses small fixture instances to validate parser, normalized schema, independent feasibility checks, runner behavior, and report output. These fixtures are not a substitute for official Solomon or Li & Lim certification. Official dataset download URLs, checksums, and reference-solution provenance must be locked before publishing academic-grade gap claims.

Current `our-dispatch-v2` and `ortools-baseline` runner modes use a deterministic normalized baseline route. The next production step is wiring `ExternalBenchmarkToDispatchCaseAdapter` into the real Dispatch V2 solver path and adding a real OR-Tools/PyVRP baseline runner.

## Smoke Command

```bash
python scripts/run_external_benchmark_certification.py --suite li-lim --preset preset:smoke --solver our-dispatch-v2 --mode benchmark-native --time-limit 30s
python scripts/run_external_benchmark_certification.py --suite solomon --preset preset:smoke --solver our-dispatch-v2 --mode benchmark-native --time-limit 30s
```
