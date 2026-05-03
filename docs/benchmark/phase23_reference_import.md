# Phase 23 Reference Route Import

Phase 23 prepares the system to import a known `RC101` 14-vehicle reference route, validate it, seed the route pool, and rerun set partitioning.

## Local Reference Paths

Drop a route file into one of these paths:

- `artifacts/benchmark/reference-solutions/RC101.json`
- `artifacts/benchmark/reference-solutions/RC101.txt`
- `artifacts/benchmark/reference-solutions/RC101.sol`
- `benchmarks/external/reference/RC101.json`

## Supported Formats

JSON:

```json
{"instance":"RC101","routes":[["0","1","2","0"]]}
```

Text:

```text
Route 1: 1 2 3
Route 2: 4 5 6
```

Depot `0` is added automatically when missing.

## Commands

```powershell
py -3.13 scripts/build_phase23_reference_source_manifest.py --instance RC101 --output-dir artifacts/benchmark/community-phase23-reference-sources-v1
py -3.13 scripts/import_phase23_reference_solution.py --instance RC101 --data-source auto --seed-dir artifacts/benchmark/community-phase20-reference-offline-v1 --output-dir artifacts/benchmark/community-phase23-reference-import-v1
py -3.13 scripts/build_phase23_reference_gate.py --candidate-dir artifacts/benchmark/community-phase23-reference-import-v1 --output-dir artifacts/benchmark/community-phase23-reference-gate-v1
```

With an explicit reference file:

```powershell
py -3.13 scripts/import_phase23_reference_solution.py --instance RC101 --data-source auto --reference artifacts/benchmark/reference-solutions/RC101.txt --seed-dir artifacts/benchmark/community-phase20-reference-offline-v1 --output-dir artifacts/benchmark/community-phase23-reference-import-v1
```

## Gate

- `PASS`: reference route is feasible and reduces vehicle gap.
- `PASS_WITH_LIMITS`: importer works but reference route is missing or does not improve gap.
- `FAIL`: final infeasible, gap regression, or feasible reference could not be imported.

## Current Purpose

This phase is expected to be `PASS_WITH_LIMITS` until a real `RC101` 14-vehicle route is provided. Once that file exists, rerun Phase 23, then rerun Phase 21 and Phase 22.

## Current Result

- Source manifest: `artifacts/benchmark/community-phase23-reference-sources-v1/phase23_reference_source_manifest.md`
- Gate artifact: `artifacts/benchmark/community-phase23-reference-gate-v1/phase23_reference_gate.md`
- Verdict: `PASS_WITH_LIMITS`
- Gap seed/after: `2/2`
- Reference available/feasible: `false/false`
- Route pool before/after: `267/267`
- Best label: `phase23-seed-incumbent`
- Warning: `phase23-reference-route-missing`

The importer, diagnostics, source manifest, and gate are now ready. The remaining action is to place a real `RC101` reference route file in one of the supported local paths and rerun this phase.

## Reference Route Result

- Reference file: `artifacts/benchmark/reference-solutions/RC101.txt`
- Gate artifact: `artifacts/benchmark/community-phase23-reference-gate-with-rc101-v1/phase23_reference_gate.md`
- Verdict: `PASS`
- Gap seed/after: `2/0`
- Reference available/feasible: `true/true`
- Reference vehicle count: `14`
- Imported routes: `10`
- Route pool before/after: `267/277`
- Best label: `phase23-set-partitioning-reference-pool`

The route source uses depot/customer IDs shifted by `+1`; the local file maps every non-depot ID by `-1` so it matches this repo's Solomon parser (`0` depot, `1..100` customers). The imported reference validates under the repo checker and removes the `RC101` BKS blocker.
