# System Architecture

## Purpose

IntelligentRouteX is a production-oriented realtime food dispatch and route optimization system. The system must optimize real dispatch quality, not only benchmark scores.

Primary goals, in priority order:

1. accurate dispatch decisions;
2. beautiful and low-risk routes;
3. fast realtime response;
4. strong baseline and public benchmark competitiveness;
5. reliable evidence through artifacts and replay validation.

## Core Production Problem

Food orders do not always arrive as a large static batch. Orders arrive continuously, sparsely and unevenly across regions. A production system must therefore avoid two bad extremes:

- dispatching every order immediately and losing good bundle opportunities;
- waiting for an artificial large batch and increasing pickup wait or order-to-delivery time.

The required architecture is a hybrid online optimizer:

- event-driven fast dispatch;
- rolling horizon state;
- adaptive micro-batching;
- active-route insertion and repair;
- bounded mini exact refinement;
- asynchronous deep improvement;
- ML-assisted ranking and risk prediction.

LLM is disabled by policy for both online dispatch and offline benchmark/report flows. Dispatch decisions must be deterministic, replayable and provider-independent. If an LLM mode is configured accidentally, the decision resolver falls back to the deterministic legacy path with reason `llm-disabled-by-policy` and no authoritative stage is applied.

## Runtime Flow

1. **Event Intake**
   - Receives new orders, driver status changes, restaurant readiness updates, traffic/weather changes and route state updates.
   - Events may come from API calls or Kafka streaming topics.

2. **Rolling Horizon State**
   - Maintains pending orders, active courier routes, driver availability, restaurant readiness and current risk context.
   - Decides whether an order should be dispatched now, held briefly, added to a micro-batch, or used to trigger active-route reoptimization.

3. **Adaptive Hold Window**
   - Urgent orders dispatch immediately.
   - Sparse low-opportunity orders receive little or no hold.
   - Dense compatible orders may receive a short hold window.
   - Bad traffic/weather and low promise slack reduce holding.

4. **Candidate Generation**
   - Generates single-order assignments, pair bundles, micro-bundles, active-route insertions and route variants.
   - Applies hard feasibility and dominance pruning before expensive optimization.

5. **Hybrid Selector**
   - Selects conflict-free proposals using a unified objective.
   - Uses greedy incumbent plus mini exact refinement when the candidate pool is small enough.
   - Rejects exact output if it is worse than the incumbent.

6. **Active Route Repair**
   - Performs bounded local changes on running courier routes.
   - Supports precedence-aware pickup/dropoff repair, relocate, swap, regret reinsertion and LNS-style improvement.
   - Applies changes only when hard violations remain zero and OTD/route stability gates pass.

7. **Dispatch Output**
   - Emits selected dispatch proposals, route state updates, decision metadata and optional training traces.

## Kafka / Big Data / Load Balancing

Streaming is optional and disabled by default for local development and benchmarks.

Production streaming direction:

- Kafka input topics for dispatch/order/driver/traffic/weather events;
- Kafka output topics for dispatch decisions;
- DLQ topics for rejected or backpressured events;
- per-key routing by region/order/driver where needed;
- configurable max in-flight backpressure;
- optional file-lake JSONL sink for dispatch results and ML training traces;
- stateless dispatch workers behind load balancing with shared external state where required.

Current remaining streaming gaps:

- add stronger embedded Kafka end-to-end tests;
- carry real selector training traces through final result objects into the sink;
- add production-grade observability dashboards for lag, throughput, rejected events and p95/p99 latency.

## Production Quality Rules

- Runtime architecture is the source of truth; benchmarks only measure it.
- Do not change benchmark thresholds to fake progress.
- Do not hardcode by benchmark instance, BKS, city or region.
- ML may rank, prune and predict risk, but hard feasibility remains deterministic.
- LLM must not run online or offline; no provider preflight, prompt validation or LLM authority is part of the supported optimizer path.
- Every quality claim must be backed by artifact paths and measured deltas.
- Do not claim full PASS unless the latest artifacts prove it.
