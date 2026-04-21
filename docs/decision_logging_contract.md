# Dispatch V2 Decision Logging Contract

## Core Train Logs

These logs are the training source of truth:

- `decision_stage_input`
- `decision_stage_output`
- `decision_stage_join`
- `dispatch_execution`
- `dispatch_outcome`

## Route Logs

- `route_leg_vector_trace`
- `route_vector_summary_trace`
- `route_selection_trace`
- `route_outcome_trace`

## LLM Sidecar Logs

- `llm_request_meta`
- `llm_usage_meta`
- `llm_context_selection_trace`
- `llm_context_fetch_trace`
- `llm_reasoning_cycle_trace`

## Rules

- Training data must be built from normalized logs only.
- Raw prompts and raw provider prose must not become training labels.
- `decision_stage_join` is the canonical bridge between stage output and actual runtime outcome.
- File naming should remain `traceId-stageKey.json` under `decision-stage/<family>/`.

## Retention Expectations

- Logs may be stored under the existing feedback base directory.
- Builders must tolerate partial families and skip incomplete traces rather than failing the whole batch.
