# Dispatch V2 Prompt Redesign Validation

This document defines the validation rail for the multi-prompt, multi-stage redesign introduced by commit `b2c69aa6`.

The goal is narrower than authority rollout:

- prove the new prompt system is resource-backed and stage-specific
- measure prompt metadata and context coverage at stage granularity
- surface fallback and evidence gaps honestly
- produce benchmark artifacts that can later support authority decisions

This rail does not widen `llm-authoritative` by itself.

## Target Stages

The default validation set is:

1. `pair-bundle`
2. `route-generation`
3. `route-critique`
4. `scenario`
5. `final-selection`

## Required Evidence

Each validated stage should emit or recover:

- `promptSpecVersion`
- `stagePromptChecksum`
- `packetTemplateChecksum`
- `candidateCountSeen`
- `comparisonPackCoverage`
- `geospatialCoverage`
- `missingContextFlags`
- stage fallback usage and reason
- selected and non-selected candidate evidence
- assessment richness based on strict `stage_output_v1` item fields

If prompt identity metadata is absent, the result is an evidence gap, not a silent pass.

## Verdict Semantics

Per-stage validation uses:

- `PASS`
- `PASS_WITH_LIMITS`
- `EVIDENCE_GAP`
- `FAIL`

`PASS_WITH_LIMITS` means evidence exists but coverage or richness is still partial.
`EVIDENCE_GAP` means the stage does not have enough prompt-era evidence to make a fair claim.

## Artifact Outputs

The validation runner writes:

- `artifacts/benchmark/prompt-redesign/prompt-redesign-validation-<timestamp>.json`
- `artifacts/benchmark/prompt-redesign/prompt_redesign_validation_report.md`

The Markdown report is the operator summary.
The JSON artifact is the canonical evidence payload.

## Default Execution Model

The validation runner uses a hybrid evidence model:

- read baseline evidence from existing benchmark roots
- optionally run a fresh small benchmark matrix for the target stages
- merge both into one stage-level report

Default fresh-cell mapping:

- `pair-bundle` -> `normal-clear / S / llm-shadow / controlled`
- `route-generation` -> `heavy-rain / S / llm-shadow / controlled`
- `route-critique` -> `traffic-shock / S / llm-shadow / controlled`
- `scenario` -> `forecast-heavy / S / llm-shadow / controlled`
- `final-selection` -> `normal-clear / S / llm-shadow / controlled`

This keeps the rail in validation scope and avoids coupling it to authority expansion.
