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

- `smoke`: smallest evidence-producing run. Runs Solomon/Li-Lim smoke, Homberger 200 evidence checks, MDRPLib public smoke data, ICAPS DPDP public smoke data, one DPDP stress case, and HCM `normal-clear/S/full-system`.
- `core`: expands academic core, all Homberger sizes, MDRP 10 placeholder slots, ICAPS 5 placeholder slots, DPDP stress matrix, and HCM `S,M` mode comparison.
- `full`: same as core plus HCM `L` size.

## Verdict Rules

- `PASS`: all required rows are feasible, hard violations are zero, objective gaps are within thresholds, and no critical blocker remains.
- `PASS_WITH_LIMITS`: feasible evidence exists but some rows have high gap, lite/fallback runtime, timeout with clear report, or missing optional official data.
- `FAIL`: any capacity, time-window, pickup-before-dropoff, active-route-corruption, or unexplained selected-route fallback violation appears.
- `EVIDENCE_GAP`: official data, parser, checker, or baseline is missing. Evidence gaps are reported explicitly and are not converted into synthetic passes.

## Current Known Gaps

- Homberger rows now parse and solve directly from `benchmarks/external/official/homberger/*.txt`; SINTEF direct download is commonly blocked by browser challenge, so the suite keeps rows as `EVIDENCE_GAP` until official files are placed there.
- MDRPLib smoke data is downloaded from Grubhub `mdrplib` public instances and checked with a deterministic structural meal-delivery baseline. This is evidence, but not yet a production rolling optimizer, so rows stay `PASS_WITH_LIMITS`.
- ICAPS DPDP smoke data is downloaded from Huawei Noah/Xingtian DPDP competition benchmark files and checked by a deterministic rolling-horizon baseline with vehicle state continuity, active-route commitment, replan latency, route stability, tardiness, and hard violation metrics. It remains `PASS_WITH_LIMITS` because it is a baseline checker, not the production dynamic optimizer.
- HCM full-system smoke currently has GreedRL `runtimeMode=native` in the latest preflight artifact. Keep `scripts/check_greedrl_native_runtime.py` in the closure flow so future runs do not silently regress to lite or fallback runtime.


## Unified Scorecard

Use `--emit-scorecard` to add `certification_scorecard.json` and `certification_scorecard.md` beside the suite outputs. The scorecard does not replace the certification verdict; it groups evidence into feasibility, optimality, food-delivery quality, dynamic quality, road realism, and system reliability so the next blocker is explicit.

The scorecard maps blockers to action lanes:

- `data-closure`: missing official benchmark data, such as Homberger files.
- `academic-global-consolidation`: vehicle-count or route-compression gap versus best known solutions.
- `food-delivery-objective`: MDRPLib is still structural/baseline evidence rather than production optimizer quality.
- `dynamic-replan-policy`: ICAPS evidence is still baseline rolling-horizon rather than full dynamic optimizer quality.
- `road-native-quality`: HCM selected routes used road fallback or weak road evidence.
- `worker-runtime-stability`: local ML/runtime attach is incomplete or GreedRL is still lite.

## Command

```powershell
python scripts/download_certification_benchmark_data.py --groups mdrplib,icaps,homberger
python scripts/check_greedrl_native_runtime.py --output artifacts/benchmark/full-system-e2e/greedrl_native_runtime_report.json
python scripts/run_dispatch_benchmark_certification_suite.py --level smoke --solver our-dispatch-v2 --time-limit 30s --output-root artifacts/benchmark/certification-suite --emit-scorecard
```
