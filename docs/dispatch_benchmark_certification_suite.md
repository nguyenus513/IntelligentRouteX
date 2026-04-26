# Dispatch Benchmark Certification Suite

This suite is the top-level certification rail for Dispatch V2 routing, pickup/dropoff, dynamic dispatch, and HCM road-native food delivery evidence. It intentionally separates academic benchmark-native scoring from road-native HCM scoring so best-known-solution gaps remain meaningful.

## Stages

| Stage | Benchmark group | Purpose | Required evidence |
| --- | --- | --- | --- |
| A | Solomon VRPTW, Li & Lim PDPTW | Academic correctness for time windows, capacity, vehicle count, distance, and pickup/dropoff precedence | normalized instance, solution, feasibility metrics, objective gap |
| B | Gehring & Homberger VRPTW | Scale from 200 to 1000 customers | official instances, runtime/memory/timeout evidence |
| C | Grubhub MDRP / MDRPLib | Meal-delivery constraints: ready time, courier shift, max delay, service times | official data, MDRP parser/checker, insertion baseline |
| D | ICAPS DPDP and generated DPDP stress | Dynamic rolling-horizon dispatch and replan stability | official DPDP data or generated stress metrics |
| E | HCM Road-Native Food Delivery | Local realistic OSRM/traffic/weather/full-system evidence | road-native full-system artifacts and visual evidence |

## Levels

- `smoke`: smallest evidence-producing run. Runs Solomon/Li-Lim smoke, Homberger 200 placeholders, MDRP smoke placeholders, ICAPS smoke placeholders, one DPDP stress case, and HCM `normal-clear/S/full-system`.
- `core`: expands academic core, all Homberger sizes, MDRP 10 placeholder slots, ICAPS 5 placeholder slots, DPDP stress matrix, and HCM `S,M` mode comparison.
- `full`: same as core plus HCM `L` size.

## Verdict Rules

- `PASS`: all required rows are feasible, hard violations are zero, objective gaps are within thresholds, and no critical blocker remains.
- `PASS_WITH_LIMITS`: feasible evidence exists but some rows have high gap, lite/fallback runtime, timeout with clear report, or missing optional official data.
- `FAIL`: any capacity, time-window, pickup-before-dropoff, active-route-corruption, or unexplained selected-route fallback violation appears.
- `EVIDENCE_GAP`: official data, parser, checker, or baseline is missing. Evidence gaps are reported explicitly and are not converted into synthetic passes.

## Current Known Gaps

- Homberger official data is not present under `benchmarks/external/official/homberger/`.
- MDRPLib official data and parser/checker are not present.
- ICAPS DPDP official data and rolling-horizon checker are not present.
- HCM full-system currently uses `GreedRL runtimeMode=lite` when native Windows Torch is blocked by Windows Application Control.

## Command

```powershell
python scripts/run_dispatch_benchmark_certification_suite.py --level smoke --solver our-dispatch-v2 --time-limit 30s --output-root artifacts/benchmark/certification-suite
```
