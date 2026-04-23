# Prompt Redesign Validation Report

- generatedAt: `2026-04-23T00:32:14.144768+00:00`
- validationCommit: `b2c69aa6`
- baselineRoots: `artifacts\benchmark\phase2-live3`
- validationRoots: `artifacts\benchmark\prompt-redesign\current\live`
- rerunExecuted: `False`

This report validates stage-level prompt redesign evidence. It is not an authority-expansion report.

## Stage Verdicts

| stage | verdict | baseline | validation | prompt checksum | packet checksum |
|---|---|---:|---:|---|---|
| `pair-bundle` | `FAIL` | 1 | 1 | `e1865fafdc122706fcb918025248907b0b40b23d9c394f3b593e3a9dc905c588` | `7d4a8060a93fbf9cfadeeb94853a2911d4b492b47d1ccabb0741c3eac2457364` |
| `route-generation` | `EVIDENCE_GAP` | 1 | 1 | `19293ea7d58086450f5fb8933301f6bf8188710cf305a27a7dc23c40fd362292` | `7d4a8060a93fbf9cfadeeb94853a2911d4b492b47d1ccabb0741c3eac2457364` |
| `route-critique` | `EVIDENCE_GAP` | 1 | 0 | `missing` | `missing` |
| `scenario` | `EVIDENCE_GAP` | 0 | 0 | `missing` | `missing` |
| `final-selection` | `EVIDENCE_GAP` | 1 | 0 | `missing` | `missing` |

## Notes

### `pair-bundle`
- `normal-clear/S/llm-shadow` context=`PASS` fallback=`FAIL` assessment=`PASS` overall=`FAIL`
  candidateCountSeen=12 comparisonCoverage=1.0 geospatialCoverage=1.0
  fallbackReason=`provider-http-error` richnessScore=`1.0` selected/nonSelected=`12/11`
- baseline evidence count: `1`

### `route-generation`
- `normal-clear/S/llm-shadow` context=`PASS` fallback=`EVIDENCE_GAP` assessment=`EVIDENCE_GAP` overall=`EVIDENCE_GAP`
  candidateCountSeen=4 comparisonCoverage=1.0 geospatialCoverage=1.0
  fallbackReason=`` richnessScore=`None` selected/nonSelected=`0/0`
- baseline evidence count: `1`

### `route-critique`
- validation evidence: missing
- result: `EVIDENCE_GAP`

### `scenario`
- validation evidence: missing
- result: `EVIDENCE_GAP`

### `final-selection`
- validation evidence: missing
- result: `EVIDENCE_GAP`
