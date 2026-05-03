# Community Benchmark Inventory

Phase 8 uses the benchmark assets already present in the repository instead of inventing a new internal-only benchmark.

## Available Community Suites

| Suite | Path | Parser | Runner | Scope |
|---|---|---|---|---|
| Solomon VRPTW fixtures | `benchmarks/external/solomon/fixtures` | `scripts/parse_solomon_vrptw.py` | `scripts/run_external_benchmark_certification.py` | VRPTW smoke: `C101`, `R101`, `RC101` |
| Li & Lim PDPTW fixtures | `benchmarks/external/li-lim-pdptw/fixtures` | `scripts/parse_li_lim_pdptw.py` | `scripts/run_external_benchmark_certification.py` | PDPTW smoke: `LC101`, `LR101`, `LRC101` |
| Official Solomon mirror | `benchmarks/external/official/solomon` | `scripts/parse_solomon_vrptw.py` | `scripts/run_external_benchmark_certification.py` | Larger certification when data is present |
| Official Li & Lim mirror | `benchmarks/external/official/li-lim-pdptw` | `scripts/parse_li_lim_pdptw.py` | `scripts/run_external_benchmark_certification.py` | Larger PDPTW certification |
| Homberger archives | `benchmarks/external/official/homberger/archives` | not hot-path in Phase 8 | deferred | Scale benchmark after smoke gate |

## Existing Baselines

- `our-dispatch-v2`: repo dispatch adapter for benchmark-native certification.
- `ortools-baseline`: Python OR-Tools routing baseline when dependency is available.
- `pyvrp-baseline`: evidence-gap safe placeholder unless PyVRP bridge/dependency is installed.

## Phase 8 Gate Contract

- Smoke must produce JSON artifacts for both Solomon and Li & Lim.
- Hard feasibility violations must be zero for PASS rows.
- Evidence gaps are allowed only for optional external baselines, not for `our-dispatch-v2` smoke fixtures.
- Runtime must stay under the configured time limit per instance.
- PASS_WITH_LIMITS is acceptable only when feasible but above best-known vehicle/objective targets.
