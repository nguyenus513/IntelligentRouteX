# IRX Documentation Index

This directory is the canonical documentation set for IntelligentRouteX.

## Recommended reading order

1. `SYSTEM_OVERVIEW.md` — current system status and certified capabilities.
2. `ARCHITECTURE.md` — technical architecture and data flow.
3. `API_REFERENCE.md` — locked API contract.
4. `API_EXAMPLES.md` — copy/paste API examples.
5. `PLAYGROUND.md` — demo guide for `/playground`.
6. `OPERATIONS.md` — local startup, testing, shutdown, troubleshooting.
7. `BENCHMARKS.md` — evidence summary and limitations.
8. `ADAPTIVE_ML_POLICY.md` — Adaptive ML policy role and evidence.
9. `BIGDATA_LITE_API.md` — batch/runtime data handling.
10. `RELEASE.md` — release package structure.
11. `THESIS_GUIDE.md` — Java thesis/write-up guide.

## Current milestone

`v0.9.9.7-production-docs-rewrite` consolidates legacy milestone docs into this canonical set.

## Main commands

```powershell
.\scripts\irx.ps1 up
.\scripts\irx.ps1 test -Quick
.\scripts\irx.ps1 down
.\scripts\irx.ps1 package
```

## Evidence artifacts

- One-click: `artifacts/test-reports/v0.9.9.6-one-click-start/one-click-gate-summary.json`
- Playground: `artifacts/test-reports/v0.9.9.5-irx-playground/playground-summary.json`
- API contract: `artifacts/test-reports/v0.9.9.4-api-contract-final/api-contract-summary.json`
- BigData-lite: `artifacts/test-reports/v0.9.9.3-bigdata-lite-api/final-bigdata-lite-api-summary.json`
- Production runtime: `artifacts/test-reports/v0.9.9.2-production-runtime/final-production-runtime-summary.json`
- Adaptive ML quality: `artifacts/test-reports/adaptive-ml-policy/v0.9.9-quality-seeking-final-summary.json`
- Final certification: `artifacts/test-reports/final-certification/final-certification-summary.json`
