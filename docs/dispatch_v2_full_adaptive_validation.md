# Dispatch V2 Full-Adaptive Validation

This document defines the evidence rail for `dispatch-v2-full-adaptive`.

The goal is narrow and operational:

- prove the benchmark harness can really run the adaptive profile
- show which heavy ML workers were skipped or escalated per case
- compare adaptive latency and quality against a non-adaptive comparison root when available
- keep conclusions honest when trace evidence is missing

This rail is not a new benchmark framework.
It reuses the existing Dispatch V2 benchmark smoke runner and adds a report layer on top.

## Target Cases

The rail is intentionally small:

1. `normal-clear / S / controlled`
2. `heavy-rain / S / controlled`
3. `traffic-shock / S / controlled`
4. `forecast-heavy / S / controlled`

Default benchmark mode:

- baseline: `C`
- decision mode: `llm-authoritative`
- prompt family: `v2`

## Required Evidence

Each adaptive case should recover:

- benchmark result JSON for the case
- `adaptive_compute_trace` rows under `decision-stage`
- worker device audit fields from `workerStatusSnapshot`
- worker audit provenance fields: `workerAuditPresent`, `workerAuditSource`, `workerAuditMissingFields`
- selected proposal count
- executed assignment count
- robust utility summary
- latency from benchmark timestamps

When comparison roots are available, the report should also compare:

- total dispatch latency
- selected and executed counts
- robust utility average

## Artifact Outputs

- `artifacts/benchmark/full-adaptive/full_adaptive_validation-<timestamp>.json`
- `artifacts/benchmark/full-adaptive/full_adaptive_validation_report.md`

The JSON payload is the canonical artifact.
The Markdown report is the operator summary.

## Verdict Semantics

Case verdicts use:

- `PASS`
- `PASS_WITH_LIMITS`
- `REGRESSION_RISK`
- `EVIDENCE_GAP`

Interpretation:

- `PASS`: adaptive trace exists, dispatch stayed usable, and skip/escalate evidence is visible without worker audit gaps.
- `PASS_WITH_LIMITS`: adaptive evidence exists, but latency gain or skip behavior is not yet convincing, or worker audit propagation is still incomplete.
- `REGRESSION_RISK`: quality or execution clearly regressed, attach failed, or the run timed out.
- `EVIDENCE_GAP`: adaptive benchmark or adaptive trace evidence is missing.

## Execution Model

The runner supports two modes:

- `adaptive-only`
- `paired`

`paired` is the default.

In rerun mode the runner writes to:

- `artifacts/benchmark/full-adaptive/live/full-adaptive/`
- `artifacts/benchmark/full-adaptive/live/pre-adaptive/`

The adaptive rerun passes `--profile dispatch-v2-full-adaptive`.
The comparison rerun omits the profile on purpose.
