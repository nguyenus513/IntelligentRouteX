# Phase 78 Monitoring And SLA Dashboard

Production integration requires runtime and SLA observability before any main-dispatch rollout.

## Required Runtime Metrics

- `runtimeMs` p50/p95/p99;
- timeout count;
- overBudget count;
- stage runtime breakdown;
- incumbent cache hit rate;
- fallback count and fallback reason distribution;
- hard violation count;
- objective regression rejection count.

## Required Dispatch/SLA Metrics

- estimated delivery time mean/p95/p99;
- pickup delay mean/p95;
- dropoff delay mean/p95;
- late order rate;
- risk-weighted late rate;
- batching ratio;
- driver utilization;
- driver load balance;
- route churn from active route changes;
- rejected/unassigned orders.

## Required Alerts

Alert when:

- hard violations > 0;
- overBudget > 0 above tolerance;
- fallback rate spikes;
- p95 or p99 delivery time regresses;
- late order rate regresses;
- checker or matrix provider unavailable;
- live adapter validation fails.

## Dashboard Slices

Metrics should be sliceable by:

- region;
- hour of day;
- peak/rain traffic context;
- restaurant;
- driver cohort;
- cancellation-risk bucket;
- shadow/canary/main mode.

## Current Status

Benchmark scorecards and synthetic food metrics exist. Live monitoring, alerting, and SLA dashboards remain required before production-main readiness.
