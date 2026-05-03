# Benchmark Architecture

## Purpose

Benchmarks measure whether runtime and algorithm changes improve real quality. They must not become the source of fake progress.

Rules:

- do not tune thresholds to claim PASS;
- do not hardcode benchmark instances or BKS values;
- every claim must cite artifact paths and measured deltas;
- full PASS can only be claimed if current artifacts prove it.
- LLM benchmark cells, provider preflight and prompt-validation rails are disabled by policy; artifacts should report deterministic `legacy` decision mode unless a future policy explicitly reintroduces non-LLM modes.

## Academic Benchmark

Academic benchmark measures routing solver strength against public or known-hard routing families.

Typical coverage:

- Solomon;
- Li-Lim;
- Homberger VRPTW;
- MDRPLib;
- ICAPS / DPDP;
- stochastic and SVRP-style community cases.

What it measures:

- vehicle-count gap;
- distance/objective gap;
- hard violations;
- competitiveness against BKS or strong baselines;
- robustness across C/R/RC-style structures.

Current meaning:

- academic = routing algorithm competitiveness;
- current weaknesses are `vehicle-count-gap`, `strong-baseline-gap` and `max-quality-not-close-to-bks`.

## Food Dispatch Quality Benchmark

Food dispatch benchmark measures production dispatch quality, not only VRP score.

Main layers:

- `bundleQuality`;
- `driverAssignmentQuality`;
- `anchorQuality`;
- `pickupSequenceQuality`;
- `dropoffSequenceQuality`;
- `orderToDeliveryQuality`.

Important blockers:

- `food-quality-target-gap`;
- `anchor-quality-target-gap`;
- `order-to-delivery-quality-target-gap`.

The most important current food bottleneck is order-to-delivery quality, especially p95/tail behavior.

## Route Beauty / Traffic / Weather Benchmarks

Route quality is measured beyond raw travel time.

Metrics include:

- detour ratio;
- straightness;
- turn count;
- sharp turns;
- zigzag behavior;
- traffic exposure;
- weather exposure;
- route-condition robustness.

Standalone route beauty can pass while elite readiness still reports evidence gaps if pair count or region coverage is too low.

## ML Intelligence Benchmark

ML benchmark proves whether ML adds measurable value.

It should verify:

- required ML dependencies are available;
- local policy adapters are connected;
- worker readiness is audited;
- ML beats or improves over no-ML / heuristic-only baselines;
- negative results are reported honestly.

Current known blockers:

- `ml-value-not-proven`;
- `rl4co-package-not-installed`.

## Dynamic Dispatch Benchmark

Dynamic dispatch benchmark measures online behavior under changing state.

It should verify:

- no hard violations;
- stable routes;
- safe reassignment behavior;
- responsiveness to new orders;
- traffic/weather changes;
- sparse and burst order scenarios.

## Runtime Benchmark

Runtime benchmark measures whether quality can be achieved within production budgets.

Important metrics:

- p50/p95/p99 latency;
- candidate count;
- solver timeout rate;
- cache hit rate;
- in-flight event pressure;
- Kafka lag when streaming is enabled;
- memory/CPU behavior.

Runtime improvement should come from caps, pruning, cache, warm-start and anytime behavior, not by removing quality logic.

## Optimizer Targeted Validation

Use `scripts/run_optimizer_targeted_validation.ps1` before moving to a new optimizer phase. The script stops stale Gradle daemons, compiles tests, then runs the focused repair, selector, active, rolling and core selector slices.

On Windows, cold Gradle startup can exceed short CLI timeouts because daemon startup, dependency transforms and test report cleanup may dominate the first run. This is not a dispatch runtime regression. Use a command timeout of at least `300s` for cold runs; warm runs should complete much faster.

If a previous timeout leaves test result files locked, run `.\gradlew.bat --stop` or rerun `scripts/run_optimizer_targeted_validation.ps1` without `-NoStopDaemon`.

## Elite Benchmark

Elite benchmark is the full-system scorecard. It combines:

- academic routing quality;
- food bundle quality;
- driver assignment quality;
- anchor quality;
- pickup/dropoff sequencing;
- order-to-delivery quality;
- route beauty;
- traffic/weather handling;
- ML intelligence;
- dynamic dispatch;
- baseline competitiveness;
- evidence depth;
- runtime quality;
- system reliability.

In short:

- academic = solver/routing competitiveness;
- elite = full production dispatch readiness.

## Latest Session Snapshot

Latest reviewed state during the 2026-05-03 session:

- shard20 community gate: `PASS`, `5/15/0` wins/ties/losses, `0` hard violations, `0.0` wall-clock overrun rate;
- shard60 community gate: `PASS`, `8/52/0` wins/ties/losses, `0` hard violations, `0.0` wall-clock overrun rate;
- overnight full large community gate: `FAIL`, `31/310/19` wins/ties/losses, `0` hard violations, `0.0` wall-clock overrun rate;
- full overnight bottleneck: Li-Lim `LRC/LC/LR` quality, especially vehicle-count repair and distance polish;
- runtime is not the current blocker; quality and evidence depth are the current blockers.

Important artifacts:

- `artifacts/benchmark/community-phase25-final-shard20-gate-v2/phase15_large_benchmark_gate.md`
- `artifacts/benchmark/community-phase26-shard60-gate-v2/phase15_large_benchmark_gate.md`
- `artifacts/benchmark/community-phase27-overnight-full-gate-v1/phase15_large_benchmark_gate.md`
- `artifacts/benchmark/community-phase27-overnight-full-report-v1/phase15_large_benchmark_report.json`

## Optimization Roadmap

Next integrated optimization priorities:

1. reduce full overnight vehicle-count losses with stronger LRC route ejection and pair-aware regret insertion;
2. improve same-vehicle distance losses above `1%` with bounded cross-route pair relocate and intra-route polish;
3. reduce Li-Lim evidence gaps by improving solver fallback evidence and dataset coverage;
4. keep runtime stable with wall-clock overrun rate at `0.0` while improving route quality;
5. preserve shard20/shard60 gates as regression guards before another overnight run;
6. prove ML value only through ablation against the solver-first baseline.
