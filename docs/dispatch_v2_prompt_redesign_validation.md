# Dispatch V2 Prompt Redesign Validation

This document defines the validation rail for the stage-specific prompt redesign.

The rail is intentionally narrower than authority rollout:

- prove prompt identity is locked per stage and per prompt family
- compare `v2` and `v3` on the same small benchmark cells
- recover session-safety metadata for `v3`
- report fallback, evidence gaps, and richness honestly

This rail does not widen `llm-authoritative` by itself.

## Scope

Default target stages:

1. `pair-bundle`
2. `route-generation`
3. `route-critique`
4. `scenario`
5. `final-selection`

Prompt-family modes:

- `v2`
- `v3`
- `both`

`both` is the default because the report is designed for paired evidence, not isolated prompt snapshots.

## Required Stage Evidence

Each validated stage should emit or recover:

- `promptFamily`
- `promptSpecVersion`
- `stagePromptChecksum`
- `packetTemplateChecksum`
- `candidateCountSeen`
- `comparisonPackCoverage`
- `geospatialCoverage`
- `missingContextFlags`
- `skillSetVersion` and `skillIdsActivated` when `promptFamily=v3`
- `sessionStoreEnabled`
- `sessionNamespace`
- `sessionReadRefs`
- `sessionWriteRefs`
- `sessionRefCount`
- fallback usage and fallback reason
- selected and non-selected candidate evidence
- assessment richness derived from strict `stage_output_v1` item fields

If prompt identity metadata is absent, the result is an evidence gap, not a silent pass.

## Verdict Semantics

Per-family stage verdicts use:

- `PASS`
- `PASS_WITH_LIMITS`
- `EVIDENCE_GAP`
- `FAIL`

Paired `v2` vs `v3` comparisons use:

- `IDENTITY_ONLY`
- `RICHER_ASSESSMENT`
- `NO_CLEAR_GAIN`
- `REGRESSION_RISK`
- `EVIDENCE_GAP`

Interpretation:

- `IDENTITY_ONLY` means `v3` prompt identity and session context are visible, but there is no evidence yet of richer assessment.
- `RICHER_ASSESSMENT` means `v3` shows materially richer candidate assessment without a new fallback penalty.
- `NO_CLEAR_GAIN` means both families produced usable evidence, but the current slice does not support a quality-uplift claim.
- `REGRESSION_RISK` means `v3` is worse on fallback or overall stage verdict.
- `EVIDENCE_GAP` means the comparison is incomplete or not fair yet.

## Artifact Outputs

Prompt redesign artifacts:

- `artifacts/benchmark/prompt-redesign/prompt-redesign-validation-<timestamp>.json`
- `artifacts/benchmark/prompt-redesign/prompt_redesign_validation_report.md`

Session-safety artifacts:

- `artifacts/validation/prompt-family-v3/session-safety/session-safety-validation-<timestamp>.json`
- `artifacts/validation/prompt-family-v3/session-safety/session_safety_report.md`

The Markdown reports are operator summaries.
The JSON payloads are the canonical evidence artifacts.

## Execution Model

The prompt validation runner uses a hybrid evidence model:

- read baseline evidence from existing benchmark roots
- optionally rerun a fresh small matrix for the target stages
- merge both into one paired `v2`/`v3` report

Default fresh-cell mapping:

- `pair-bundle` -> `normal-clear / S / llm-shadow / controlled`
- `route-generation` -> `heavy-rain / S / llm-shadow / controlled`
- `route-critique` -> `traffic-shock / S / llm-shadow / controlled`
- `scenario` -> `forecast-heavy / S / llm-shadow / controlled`
- `final-selection` -> `normal-clear / S / llm-shadow / controlled`

Default rerun roots:

- `artifacts/benchmark/prompt-redesign/live/v2/`
- `artifacts/benchmark/prompt-redesign/live/v3/`

This keeps the rail in validation scope and avoids coupling it to authority expansion.
