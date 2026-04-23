# Dispatch V2 Prompt Family V3

This document defines the semantics of `promptFamily=v3`.

`v3` is intentionally gated. It is not the default runtime path.

## What V3 Adds

Compared with `v2`, `v3` adds three things:

1. stage brains
2. skill registry
3. session-bound blackboard references

The runtime contract stays stable:

- 12-stage runtime order does not change
- replay identity does not change
- transport stays `1 system + 1 user`
- output stays strict `stage_output_v1`
- fallback behavior stays stage-local

## Session Scope

`v3` session state is strictly bounded to:

- `runId`
- `tickId`
- `traceId`

This boundary is called the session namespace.

Stage-to-stage reuse is allowed only inside the same namespace.
Cross-trace, cross-tick, and cross-run reads are forbidden.

## Session Artifacts

When `promptFamily=v3` and the session store is enabled, the runtime may emit:

- `decision_session_manifest`
- `decision_session_ref_trace`
- `decision_session_stage_summary`
- `llm_skill_activation_trace`

Important fields:

- `sessionStoreEnabled`
- `sessionNamespace`
- `sessionReadRefs`
- `sessionWriteRefs`
- `sessionRefCount`

These fields exist for observability and validation. They are not authority-evidence by themselves.

## Skill Registry

`v3` can load stage-specific skill sets from resources.

Skill metadata is expected to surface:

- `skillSetVersion`
- `skillIdsActivated`

This supports paired validation of:

- prompt identity
- stage visibility
- session usage
- assessment richness

## Validation Gates

`v3` is only considered safe to widen after both rails are healthy:

1. session-safety rail
2. stage-level prompt validation rail

Minimum safety claims:

- no cross-trace contamination
- no stale session reuse across ticks or runs
- `v2` path remains session-store free
- `v3` prompt identity is visible in logs and artifacts

Quality uplift claims need separate evidence and must not be inferred from architecture alone.
