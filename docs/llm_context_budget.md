# Dispatch V2 LLM Context Budget

Each stage prompt is built from eight layers:

1. static prefix
2. dispatch context
3. stage-local candidate window
4. reference frame
5. comparison pack
6. geospatial context
7. burst context
8. upstream summary

Do not dump full runtime state or raw map tiles into any stage request.

## Static Prefix

The static prefix contains:

- stage objective
- hard constraints
- strict JSON schema
- reason code enum
- one or two short exemplars

This prefix should stay stable to improve cache locality and latency.

## Stage Budgets

- `pair-bundle`: at most 12 pairs and 12 bundles
- `anchor`: at most 6 bundles, 4 anchors per bundle
- `driver`: at most 4 bundles, 8 drivers per bundle
- `route-generation`: 1 bundle, 3 drivers, 4 alternatives
- `route-critique`: 4 route proposals
- `scenario`: 3 proposals
- `final-selection`: 3 final proposals

## Tool Fetch Rules

Tools may be used only to fetch missing detail:

- `get_bundle_details`
- `get_driver_details`
- `get_route_vector_summary`
- `get_conflict_summary`
- `get_scenario_breakdown`

Rules:

- `parallel_tool_calls = false`
- every tool response must be schema-validated
- every tool fetch must be logged to `llm_context_fetch_trace`
- tool fetch must not replace the top-K budget discipline

## Multi-Pass Stages

Selective multi-pass rollout applies to:

- `driver`
- `route-generation`
- `route-critique`
- `scenario`
- `final-selection`

Loop:

1. `propose`
2. `critique`
3. `compare`
4. `commit`
