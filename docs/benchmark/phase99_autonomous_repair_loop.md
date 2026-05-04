# Phase 99 Autonomous Final Repair Loop

Phase 99 adds a bounded local repair loop for the final decomposition blocker. It does not introduce benchmark-name branches, target vehicle forcing, comparator leakage, or background execution.

## Components

- `scripts/optimizer/phase99_exact_tw_route_finalizer.py` runs a precedence-preserving beam search over pickup/dropoff orderings for small affected routes.
- `scripts/run_phase99_autonomous_repair_loop.py` runs focused tests, runs the Li-Lim decomposition probe, classifies the blocker, and writes a patch prompt when the success gate is not reached.

## Success Gate

`PASS_STRONG` requires:

- `acceptedRecombinedCandidates >= 1`
- `timeWindowViolationCountAfter = 0`
- `hardViolations = 0`
- `rejectedByCoverage = 0`
- `rejectedBySlotOverflow = 0`
- `antiHardcodeGate = PASS`

Without `--agent-command`, the loop stops after writing the next patch prompt. With `--agent-command`, it feeds the prompt to the provided command and repeats until success or the configured iteration/wall-clock limit.

## Example

```powershell
py -3.13 scripts/run_phase99_autonomous_repair_loop.py `
  --max-iterations 3 `
  --output-dir artifacts/benchmark/phase99_autonomous_loop_v1
```
