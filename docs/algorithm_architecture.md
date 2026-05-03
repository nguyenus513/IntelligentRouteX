# Algorithm Architecture

## Hybrid Optimizer Stack

No single algorithm wins every dispatch case. IntelligentRouteX should use a hybrid stack that combines fast heuristics, rolling horizon optimization, local search, small exact solvers and ML-assisted ranking.

LLM is not part of the algorithm stack. The optimizer must be solved by deterministic feasibility checks, objective scoring, candidate generation, bounded repair and selector recombination. LLM modes are disabled online and offline because they add latency, provider dependency and non-determinism without replacing ALNS, CP-SAT, feasibility or objective logic.

Priority order:

1. decision accuracy and feasibility;
2. route beauty and risk control;
3. runtime latency;
4. baseline competitiveness;
5. evidence and reproducibility.

## Fast Path

Target budget: tens to hundreds of milliseconds.

Used when an immediate answer is required.

Algorithms:

- nearest feasible driver;
- regret insertion;
- anchor top-K scoring;
- bounded beam search;
- candidate dominance pruning;
- route beauty and risk guards;
- ML pre-ranker when confidence is sufficient.

Guarantees:

- always returns a feasible incumbent when one exists;
- never waits for a large batch;
- avoids expensive global solving on normal events.

## Rolling Horizon + Adaptive Micro-Batching

This is the main answer to sparse continuous order arrival.

Decision modes:

- `DISPATCH_NOW` for urgent or low-opportunity orders;
- `HOLD_SHORT` for orders with safe slack and bundle opportunity;
- `MICRO_BATCH` for dense compatible local clusters;
- `REOPTIMIZE_ACTIVE_ROUTE` for beneficial route insertion/repair.

Features:

- promise slack;
- ready-time compatibility;
- nearby pending orders;
- active courier proximity;
- restaurant/corridor compatibility;
- traffic/weather risk;
- historical density and tail-risk prediction.

## Bundle Optimizer

Bundle generation should be compatible multi-restaurant batching, not only same-restaurant batching.

Algorithms:

- ready-time-aware insertion;
- regret-k insertion;
- bounded beam search;
- freshness guard;
- max-delay guard;
- corridor and detour compatibility;
- set-packing selection over candidate bundles.

Objective order:

1. hard feasibility;
2. served rate;
3. p95 order-to-delivery;
4. p95 food-on-vehicle;
5. pickup wait;
6. route beauty/risk;
7. fairness/utilization.

## Anchor Selector

Anchor should not be fixed too early. The selector should keep top-K anchors and let downstream scoring choose with route/bundle context.

Anchor features:

- ready slack;
- active courier proximity;
- restaurant/courier corridor fit;
- detour risk;
- traffic risk;
- weather risk;
- boundary-cross penalty;
- expected pickup wait and OTD impact.

## Route Sequencing and Beauty

Route optimization must optimize time and shape.

Algorithms:

- pickup/dropoff precedence insertion;
- 2-opt / Or-opt for local sequence cleanup;
- cross-exchange for bounded multi-route improvement;
- k-shortest route variants;
- low-turn and corridor-fit route variants;
- dominance rules for detour, straightness, turn count, sharp turns, zigzag and traffic/weather exposure.

Route beauty must be part of runtime scoring, not only a post-benchmark metric.

## Active Route Repair / LNS

Used for already-running routes and local neighborhoods.

Operators:

- relocate order;
- swap 1-1;
- regret reinsertion;
- adjacent precedence repair;
- bounded Or-opt;
- bounded ejection chain;
- LNS destroy/repair on small affected regions.

Acceptance rule:

- hard violations must remain zero;
- p95 OTD must not worsen unless explicitly traded for a stronger feasibility objective;
- food-on-vehicle and pickup wait must be guarded;
- route churn and driver reassignment must stay bounded.

## Mini Exact Refinement

Exact solving is used only on small subproblems.

Recommended limits:

- orders `<= 30`;
- drivers `<= 20`;
- candidates `<= 300`;
- strict realtime timeout;
- best-so-far return.

Algorithms:

- bipartite matching;
- min-cost flow;
- set packing / set partitioning;
- CP-SAT or MILP only for bounded high-value subproblems.

## Academic Max-Quality Optimizer

Used to reduce strong-baseline and BKS gaps.

Required algorithms:

- ALNS;
- Shaw removal;
- worst removal;
- route elimination;
- regret-k reinsertion;
- ejection chain;
- cross-exchange;
- route pool diversity expansion;
- multi-round set partitioning;
- warm-start from previous solutions.

Goal:

- reduce vehicle-count gap;
- reduce strong-baseline gap;
- avoid case-specific rules or BKS leakage.

## ML Assist Layer

ML should make the solver faster and smarter, not replace feasibility logic.

Models to train or prove:

- hold-window predictor;
- bundle ranker;
- anchor ranker;
- route ranker;
- tail-risk predictor for OTD/freshness;
- ALNS/LNS operator policy;
- candidate pruning model.

Validation required:

- no-ML baseline;
- heuristic-only baseline;
- ML-ranker variant;
- ML + solver variant;
- ablation showing value in quality, runtime or tail-risk reduction.

## Runtime Optimization Techniques

- spatial index by grid/H3/R-tree;
- ETA and route-leg cache;
- route-shape cache;
- incremental recomputation by affected region;
- top-K candidate caps;
- early dominance pruning;
- warm-start rolling horizon;
- anytime solver behavior;
- parallel candidate scoring;
- strict p95/p99 latency budgets.
