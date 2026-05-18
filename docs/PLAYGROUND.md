# Playground

The IRX Playground is the one-screen demo at:

`http://localhost:5173/playground`

It is a frontend/API integration layer. It does not change solver/core behavior.

## What it demonstrates

- Static dispatch job through `/api/v1/static/dispatch/jobs`.
- Live rolling flow through `/api/v1/live/*`.
- Rescue flow through `/api/v1/rescue/jobs`.
- BigData-lite batch through `/api/v1/bigdata/batches`.
- Event and artifact fetching.
- Runtime metrics.
- Adaptive ML diagnostics panel.
- Baseline comparison panel.
- Raw JSON inspection.

## How to run

```powershell
.\scripts\irx.ps1 up
```

Then open `/playground`.

## Demo flow for presentation

1. Select `raw-s` and `STATIC_DISPATCH`.
2. Choose `QUALITY_SEEKING` Adaptive ML.
3. Click Run and show result summary, Adaptive ML panel, baseline panel, events, artifacts, and raw JSON.
4. Switch to `LIVE_ROLLING`, run cycle, show live state and events.
5. Switch to `RESCUE`, show `lateNotWorse` and `rescueDominanceGuard`.
6. Switch to `BIGDATA_LITE`, show batch status and paginated items.

## Evidence

`artifacts/test-reports/v0.9.9.5-irx-playground/playground-summary.json` records:

- dashboard typecheck/build PASS
- backend health PASS
- `/playground` route exists
- static/live/rescue/BigData flows PASS
- events/artifacts PASS
- Adaptive ML/baseline/result/raw JSON panels PASS
