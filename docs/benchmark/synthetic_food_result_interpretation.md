# Synthetic Food Result Interpretation

This note explains how to interpret the synthetic food VROOM comparison without overstating the result.

## Feasibility Win Vs Quality Win

A **feasibility/stability win** means a solver returns routes that satisfy hard constraints:

- exact pickup/dropoff coverage;
- pickup before dropoff;
- capacity constraints;
- time windows;
- wall-clock budget.

A **quality win** requires both solvers to be feasible first. Only then should vehicle count, distance, and objective be compared.

In the current synthetic-food full run, Phase 56F is feasible `6/6`, while VROOM hard-fails `6/6`. Therefore the correct conclusion is feasibility/stability advantage for Phase 56F; distance or vehicle-count quality remains inconclusive.

## Why VROOM Hard-Fail Is Not A Distance Comparison

When VROOM returns a route with time-window violations, its shorter distance or equal vehicle count is not a valid quality win. Infeasible routes are rejected before distance and vehicle count are considered.

Phase 59 classifies these cases as `challenger-better-feasibility`, not `challenger-quality-win-distance` or `challenger-quality-win-vehicle-count`.

## Why Matrix-Duration Mismatch Is Separate

Phase 67B separates confirmed VROOM time-window violations from semantic mismatches:

- `vroom-true-time-window-violation`: VROOM step arrivals are outside the internal node time windows.
- `matrix-duration-mismatch`: distance and duration semantics disagree enough that the comparator needs separate interpretation.

The current audit-backed result is:

| Classification | Count |
|---|---:|
| vroom-true-time-window-violation | 4/6 |
| matrix-duration-mismatch | 2/6 |
| unknown | 0/6 |

The two matrix-duration mismatch cases should not be described as confirmed true VROOM solver failures. They should be described as comparator semantics cases that require aligned distance/duration interpretation before quality scoring.

## Recommended Wording

Use this wording:

> On synthetic food scenarios, Phase 56F produces feasible routes for all six cases with hard violations `0` and overBudget `0`. VROOM returns no internally feasible solution in this run; Phase 67B confirms four true VROOM time-window violations and two matrix-duration semantic mismatches. This supports a feasibility/stability advantage for IntelligentRouteX on this synthetic suite. Quality superiority remains inconclusive because VROOM has no feasible synthetic solution for distance or vehicle-count comparison.
