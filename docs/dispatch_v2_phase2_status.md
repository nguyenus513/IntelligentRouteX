# Dispatch V2 Phase 2 Status

Status: `PASS_WITH_LIMITS`

Last verified: `2026-04-20`

## Final Verdict

Phase 2 now passes the minimum completion gate for authoritative LLM rollout:

- `llm` runtime is usable through `9router /v1/responses`
- model-family resolution now discovers and sends a namespaced model id for `gpt-5.4`
- stage-level fallback stays local to the failing stage and no longer overwrites legacy selections
- real authoritative execution is verified for:
  - `pair-bundle`
  - `final-selection`
- benchmark artifacts exist for:
  - `legacy`
  - `llm-shadow`
  - `llm-authoritative`
- normalized logs and route-vector traces can now be turned into a student-training dataset from an aggregate benchmark root

This is not marked `PASS` yet because authority coverage is intentionally limited to the first safe rollout set, and route-vector traces are not present in every benchmark cell.

`209de162` remains a keeper on `main`. It improves observability and route trace completeness, but it does not close the remaining authority gate by itself.

`b2c69aa6` is also a keeper on `main`. It changes the LLM lane from a shared prompt framework into a resource-backed multi-stage prompt system with:

- 4 global prompt packs
- 9 stage system prompts
- 9 stage packet templates
- stage-specific mission, visibility, budget, objective, and prompt metadata logging

That architecture shift is implemented. Quality uplift still needs stage-level validation evidence.

## What Changed

- `NineRouterResponsesClient` now:
  - discovers models from `/v1/models`
  - resolves `gpt-5.4` to a namespaced runtime id such as `cx/gpt-5.4`
  - uses strict structured output schemas accepted by `9router /v1/responses`
  - records configured model family, resolved model id, provider base URL, wire API, token usage, retries, and effort application
- `DispatchV2Core` authority wiring now:
  - prevents fallback LLM envelopes from being applied authoritatively
  - preserves the original final-selection solver mode instead of forcing `GREEDY_REPAIR`
- benchmark runtime/test mapping now preserves:
  - `llm-shadow`
  - `llm-authoritative`
- prompt rendering now uses:
  - resource-backed prompt specs
  - manifest-driven stage mappings
  - stage-specific visibility, budget, and objective policies
  - prompt metadata fields such as checksum and context coverage
- dataset builder now:
  - discovers nested feedback roots under an aggregate benchmark directory
  - recovers trace linkage from filenames for execution, outcome, and route-vector families
  - validates only the filtered trace set instead of failing on unrelated benchmark cells

## Prompt Redesign Validation

Prompt redesign is now implemented at the runtime layer, but it is tracked separately from authority closure.

Validation rail:

- contract: [dispatch_v2_prompt_redesign_validation.md](/E:/Code%20_Project/IntelligentRouteX/docs/dispatch_v2_prompt_redesign_validation.md)
- report artifact: [prompt_redesign_validation_report.md](/E:/Code%20_Project/IntelligentRouteX/artifacts/benchmark/prompt-redesign/prompt_redesign_validation_report.md)

Interpretation:

- implementation status: `DONE`
- stage-level quality evidence: `IN_PROGRESS`
- authority impact claim: `NOT_YET_CLOSED`

## Validation Completed

Code validation:

- `./gradlew.bat --no-daemon clean compileJava compileTestJava`
- `./gradlew.bat --no-daemon test --tests com.routechain.v2.decision.NineRouterResponsesClientTest --tests com.routechain.v2.decision.DecisionBrainResolverTest`
- `./gradlew.bat --no-daemon test --tests com.routechain.v2.DispatchV2CoreOrToolsSliceTest`
- `python scripts/test_build_dispatch_v2_student_dataset.py`

Live provider validation:

- `GET http://127.0.0.1:20128/v1/models`
- `POST http://127.0.0.1:20128/v1/responses`
- `GET https://r8cp2m4.9router.com/v1/models`
- `POST https://r8cp2m4.9router.com/v1/responses`

Both local and tunnel endpoints accepted strict Responses API calls when the resolved model id was namespaced.

## Benchmark Evidence

Primary artifact root:

- `artifacts/benchmark/phase2-live3/`

Completed matrix:

- scenarios:
  - `normal-clear / S`
  - `heavy-rain / S`
  - `traffic-shock / S`
- extra coverage:
  - `normal-clear / M`
- modes:
  - `legacy`
  - `llm-shadow`
  - `llm-authoritative`

Observed result highlights:

- `llm-authoritative` runs are real authority runs, not fallback-only runs:
  - `runAuthorityClass = AUTHORITY_REAL`
  - `authoritativeStages = [pair-bundle, final-selection]`
  - token usage is non-zero in all authoritative cells
- `llm-authoritative` fallback summary is clean in the verified cells:
  - `normal-clear / S`: `0`
  - `heavy-rain / S`: `0`
  - `traffic-shock / S`: `0`
  - `normal-clear / M`: `0`
- `llm-shadow` still shows route-generation fallback in some cells:
  - `heavy-rain / S`: `ROUTE_GENERATION -> provider-http-error`
  - `traffic-shock / S`: `ROUTE_GENERATION -> provider-http-error`

Representative artifact references:

- [dispatch-quality-summary.md](/E:/Code%20_Project/IntelligentRouteX/artifacts/benchmark/phase2-live3/dispatch-quality-summary.md)
- [normal-clear authoritative JSON](/E:/Code%20_Project/IntelligentRouteX/artifacts/benchmark/phase2-live3/dispatch-quality-normal-clear-s-llm-authoritative-controlled-c-20260420-125341.json)
- [heavy-rain authoritative JSON](/E:/Code%20_Project/IntelligentRouteX/artifacts/benchmark/phase2-live3/dispatch-quality-heavy-rain-s-llm-authoritative-controlled-c-20260420-125953.json)
- [traffic-shock authoritative JSON](/E:/Code%20_Project/IntelligentRouteX/artifacts/benchmark/phase2-live3/dispatch-quality-traffic-shock-s-llm-authoritative-controlled-c-20260420-130555.json)

## Dataset Build Evidence

Aggregate benchmark feedback can now be converted into normalized training datasets without pointing the builder at a single leaf directory.

Built datasets:

- `artifacts/benchmark/phase2-live3/dataset/llm-authoritative-all/`
  - filtered by `decisionMode = llm-authoritative`
  - required route-vector presence
  - counts:
    - `stage_inputs = 18`
    - `stage_outputs = 18`
    - `stage_joins = 18`
    - `dispatch_execution = 2`
    - `dispatch_outcomes = 2`
    - `route_vectors = 320`
- `artifacts/benchmark/phase2-live3/dataset/llm-shadow-all/`
  - filtered by `decisionMode = llm-shadow`
  - required route-vector presence
  - counts:
    - `stage_inputs = 9`
    - `stage_outputs = 9`
    - `stage_joins = 9`
    - `dispatch_execution = 1`
    - `dispatch_outcomes = 1`
    - `route_vectors = 80`
- `artifacts/benchmark/phase2-live3/dataset/llm-authoritative-normal-clear-pair-bundle/`
  - filtered by:
    - `stage = PAIR_BUNDLE`
    - `scenarioPack = normal-clear`
    - `decisionMode = llm-authoritative`
    - `authorityPhase = c`

This confirms the builder works across:

- stage filters
- scenario-pack filters
- decision-mode filters
- authority-phase filters
- route-vector availability filters

## Remaining Limits

- authoritative rollout is only proven clean for:
  - `pair-bundle`
  - `final-selection`
- `driver`, `route-critique`, `scenario`, and `route-generation` are not yet promoted to clean authoritative coverage in this report
- prompt redesign quality uplift is not considered proven until the prompt redesign validation rail records stage-level `PASS` or `PASS_WITH_LIMITS` evidence for the target stages
- route-vector traces are not emitted in every scenario/mode cell, so `route-vector-availability=required` intentionally filters out trace roots without those families
- `llm-shadow` still exhibits route-generation fallback in some live cells; this does not block the minimum gate but it does block broader authority expansion
- heavy quality harness execution on Windows is still execution-sensitive; timeout-prone runs must be classified before treating them as logic regressions

## Benchmark Execution Notes

- `DispatchQualityBenchmarkHarnessTest` timeouts are currently treated as execution-flakiness unless timeout classification proves a dispatch logic failure.
- Windows-heavy local runs should use sequential isolated cells and per-cell artifact flushing.
- Promotion decisions should read the new per-stage blocker summary before widening the authoritative stage set.

## Recommended Next Gate

Continue rollout in this order:

1. `driver`
2. `route-critique`
3. `scenario`
4. `route-generation`

Do not promote `route-generation` until the live shadow/provider-http-error cases are understood and the route-vector trace coverage is stable across the benchmark matrix.
