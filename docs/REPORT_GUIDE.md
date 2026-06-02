# IRX Report Guide

Use this document as a checklist for the graduation/project report and demo evidence.

## 1. Core Message

IRX is not a one-shot static route solver. IRX is a stateful realtime dispatch orchestrator for live logistics.

Recommended wording:

```text
IntelligentRouteX combines multi-solver seed generation, realtime rolling-horizon dispatch, aging-priority buffering, OSRM road metrics, and IRX adaptive refinement to produce stable live routes with low churn and low latency.
```

## 2. Problem Statement

Explain the production dispatch problem:

- Orders arrive continuously, not all at once.
- Drivers go online/offline and move while dispatch is running.
- Routes cannot be randomly rewritten after a driver starts moving.
- Pickup/dropoff precedence must be preserved.
- SLA/late risk must be evaluated from ETA and route sequence.
- A new order may wait in buffer briefly, but must not be forgotten.

Contrast with static VRP:

```text
Static VRP solves one fixed input once.
Live dispatch must repeatedly decide with partial knowledge, moving drivers, frozen route segments, and changing order streams.
```

## 3. Architecture To Include

Recommended diagram sections:

- React Control Tower Dashboard.
- Spring Boot API Layer.
- Live Session State.
- Aggregation Buffer.
- Aging Priority Balanced Dispatch.
- Solver Seed Race.
- IRX Refinement Ensemble.
- Dominance Guard.
- OSRM Routing Metrics.
- Event/Log/KPI stream.
- BigData-lite JSONL/runtime queue.

API-first explanation:

- FE sends orders/drivers/events to backend.
- Backend owns assignment and sequence decisions.
- FE renders backend result and OSRM geometry.
- Benchmark and live modes use comparable backend metrics.

## 4. Algorithm Sections

### Aging Priority Balanced Dispatch

Include:

- Orders enter buffer as `NORMAL`.
- Waiting time and skipped rounds increase urgency.
- Priority levels: `NORMAL`, `WARM`, `HOT`, `CRITICAL`, `FORCE_ASSIGN`.
- Older/skipped orders become harder to ignore.
- Driver balance prevents overloading one driver.

Suggested formula:

```text
urgency_score = waiting_minutes * A + skipped_rounds * B + skipped_rounds^2 * C
final_score = route_fit + urgency + driver_balance + deadline_score - route_change_penalty
```

### Multi-Solver Seed Race

Include:

- `VROOM` seed.
- `OR-Tools` seed.
- `PyVRP` seed.
- `IRX_NATIVE` seed.
- Interleaved pickup/dropoff seed when useful.

Explain that seed race gives IRX a better starting point than a single heuristic.

### IRX Refinement

Include:

- Local insertion.
- Relocate/swap/reorder.
- Route churn penalty.
- Freeze policy.
- Dominance comparator.

Candidate acceptance rules:

- No lost orders.
- No dropoff before pickup.
- No hard violation increase.
- No late increase unless explicitly justified by higher-priority objective.
- No frozen stop break.

### Late/SLA Evaluation

Late should be explained as ETA-based:

```text
arrival_time_at_dropoff > order_deadline => late order
lateness_minutes = max(0, arrival_time_at_dropoff - deadline)
```

ETA inputs:

- OSRM segment duration.
- Driver current position.
- Stop order.
- Pickup/dropoff service time.
- Driver speed profile or traffic multiplier.
- Priority/SLA class.

## 5. Best Result Evidence

Report the best run only with reproducible metadata:

- Dataset/scenario name.
- Number of orders and drivers.
- Runtime budget.
- Routing provider: OSRM or fallback.
- Solver rows: IRX, VROOM, OR-Tools, PyVRP, Nearest, One-by-one.
- Distance, late count, coverage, runtime, and P/D sequence.
- Screenshot of benchmark table.
- Screenshot of decision trace winner.
- Screenshot of live driver moving on route.

Recommended result table:

```text
Solver | Runtime | OSRM Distance | Late | Coverage | Sequence | Result
IRX    | ...     | ...           | ...  | ...      | ...      | COMPLETED
VROOM  | ...     | ...           | ...  | ...      | ...      | COMPLETED
...
```

Important: do not claim a solver is available if the runtime is missing. Mark it as environment unavailable.

## 6. Dashboard Evidence

Screenshots to capture:

- System readiness.
- Live map before dispatch.
- Buffer monitor with order priority.
- Backend route assignment trace.
- Driver tracking mode.
- Pickup completed marker removed.
- Dropoff completed marker removed.
- Benchmark comparison table.
- Decision trace final route.
- API sandbox request/response.

## 7. Current Completion Status

Completed enough for source demo:

- Backend compiles.
- Dashboard typecheck/build passes.
- Live dashboard and benchmark surfaces exist.
- Packaging scripts and smoke gates exist.
- BigData-lite runtime exists.
- LLM integration is intentionally not included.

Still not fully production/portable until runtime assets are supplied:

- Native `vroom.exe`.
- Native OSRM binaries.
- Prebuilt `.osrm` map data.
- Portable Python with PyVRP.
- Fresh-machine package smoke.

Production hardening still recommended:

- Replace in-memory/demo session state with durable store where needed.
- Add maintained Playwright E2E suite for current UI labels.
- Add solver-runtime health diagnostics per environment.
- Add larger stress gates for 1k/10k order ingestion.
- Add API auth/secrets deployment guide for real deployment.

## 8. Suggested Report Structure

1. Introduction and motivation.
2. Related work: VRP, PDPTW, rolling horizon, dispatch systems.
3. System requirements.
4. Architecture.
5. Algorithms.
6. API design.
7. Dashboard and UX.
8. Experiments and benchmarks.
9. Demo scenario.
10. Limitations.
11. Future work.
12. Conclusion.

## 9. Conclusion Wording

```text
IRX demonstrates a hybrid live dispatch platform that can receive dynamic orders and drivers, buffer and prioritize demand, compare multiple solver seeds, refine the best candidate, protect active routes with freeze policy, and return traceable realtime routing decisions for dashboard visualization.
```
