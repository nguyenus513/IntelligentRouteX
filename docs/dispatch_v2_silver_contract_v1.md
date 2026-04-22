# Dispatch V2 Silver Contract V1

Silver is normalized, join-ready data. Builders must not infer semantics from family-specific names once a canonical field exists.

## Canonical Tables

- `decision_stage_join_canonical`
  - join key: `traceId + stageName + candidateId`
  - source: decision stage input/output/join candidate rows
- `route_candidate_canonical`
  - join key: `traceId + stageName + candidateId`
  - source: route vector summaries plus grouped route stop rows
- `driver_fit_canonical`
  - join key: `traceId + stageName + candidateId`
- `bundle_geometry_canonical`
  - join key: `traceId + stageName + candidateId`
- `tile_context_canonical`
  - join key: `traceId + stageName + candidateId`
  - aggregates tile selection, tile features, and traffic context
- `teacher_trace_canonical`
  - join key: `traceId + stageName + candidateId`
  - carries `teacherKind`
- `dispatch_outcome_canonical`
  - join key: `traceId`

## Canonical Rules

- Preserve envelope fields from Bronze.
- Preserve `source`, `fallbackUsed`, and `missingReason`.
- Normalize grouped route stop information into route candidate rows.
- Keep outcome labels in `dispatch_outcome_canonical` only until Gold join time.
