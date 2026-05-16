# IRX ML-Fused Hybrid Quality Benchmark Report

## Milestone

- Commit: `81f319d72` (`Add quality benchmark mode and deep gate`)
- Benchmark modes:
  - `FAST_GATE`: regression/stability gate, synthetic matrix-first distance semantics.
  - `QUALITY_BENCHMARK`: deeper objective benchmark, `QUALITY_ROAD_MATRIX` claim type, SwapStar enabled, external contributor status recorded.
- Final solver row remains `IRX ML-Fused Hybrid`; baseline/external solvers are seed/evidence contributors only.

## FAST_GATE Result

- Artifact: `artifacts/test-reports/clean-cache-gate-summary.json`
- Dataset count: `7`
- Result: PASS
- Runtime hot: `234.693s`
- Distance objective: `7W / 0T / 0L`
- OR-Tools objective: `4W / 3T / 0L`
- Late regression: `0`
- Dominance failures: `0`
- Routing mode: `FAST_GATE_MATRIX_FIRST_SYNTHETIC`
- Distance claim type: gate stability only; not a production road-distance benchmark.

## QUALITY_BENCHMARK Result

- Artifact: `artifacts/test-reports/quality/clean-cache-gate-summary.json`
- Dataset count: `15`
- Result: PASS
- Runtime: `759.551s`
- Distance objective: `15W / 0T / 0L`
- OR-Tools objective: `10W / 5T / 0L`
- Raw distance: `10W / 0T / 5L`
- Late regression: `0`
- Dominance failures: `0`
- SwapStar attempts: `253`
- Routing mode: `QUALITY_ROAD_MATRIX`
- Distance claim type: road-matrix benchmark.

## External Contributor Status

- VROOM: `EVIDENCE_GAP` when `QUALITY_BENCHMARK` is used and no runtime is configured.
- PyVRP: `EVIDENCE_GAP` when `QUALITY_BENCHMARK` is used and no runtime is configured.
- In `FAST_GATE`, both are `DISABLED` by design.

## Why Raw-Distance Loss Is Not Failure

Raw-distance loss means a baseline route is shorter in kilometers. It is not a failure if the baseline produces more late orders or worse unified objective. IRX uses SLA-strict lexicographic selection:

1. coverage and hard feasibility,
2. late count,
3. total lateness,
4. distance,
5. load/final score.

Therefore IRX can correctly choose a slightly longer route that preserves `late0` over a shorter baseline with late deliveries.

## Known Limitations

- VROOM/PyVRP are contributor contracts with `EVIDENCE_GAP` unless runtime configuration is present.
- `FAST_GATE` is intentionally synthetic/fast and must not be used for production distance claims.
- `QUALITY_BENCHMARK` is slower by design and currently validates quality, not live latency.
- Live rolling dispatch still needs a dedicated mini-gate.
- Dashboard Victory Report should surface `why selected`, move traces, contributor status, and routing-mode warnings more clearly.

## Next Phases

1. Route benchmark/static/rescue/live through the generic `UnifiedDispatchCore.dispatch(...)` entrypoint.
2. Add runtime-ready VROOM/PyVRP availability checks and adapters.
3. Add live rolling mini system and gate.
4. Harden IRX Native route proposals with schedule/slack awareness.
5. Polish Dashboard Victory Report and final demo scripts.
