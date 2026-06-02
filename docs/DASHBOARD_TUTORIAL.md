# IRX Dashboard Tutorial

This guide explains how to run and present the IRX control-tower dashboard.

## 1. Start The System

Backend:

```powershell
.\gradlew.bat bootRun --args="--server.port=18116"
```

Frontend:

```powershell
cd playground
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Expected startup signals:

- Backend health is visible.
- Solver readiness panel shows IRX, VROOM, OR-Tools, and PyVRP availability when those runtimes are configured.
- Live tab starts with Auto Order OFF and Auto Driver OFF.
- Console/log panel does not force-scroll unless auto-scroll is enabled by the user.

## 2. Live Dispatch Flow

Use this mode to show stateful realtime dispatch, not one-shot static solving.

1. Open the Live tab.
2. Press `Start Live`; the button switches to `Stop Live`.
3. Pin drivers on the map or enable Auto Driver.
4. Pin pickup/dropoff orders on the map or enable Auto Order.
5. Confirm every manual pin is sent to backend live APIs.
6. Watch the buffer monitor: waiting orders, priority levels, skipped rounds, urgency score, and selected driver.
7. Wait for backend dispatch cycle: seed race, IRX optimization, dominance guard, final assignment.
8. Driver route starts from the current driver location, then follows pickup/dropoff sequence returned by backend.
9. Pickup marker disappears only after the driver reaches the pickup.
10. Dropoff marker disappears only after delivery completes.
11. Consumed route geometry behind the driver is removed as the driver moves.
12. Press `Stop Live` to pause the live engine.

Use `Cancel & Clear Map` when presenting a reset:

- Stops active live/demo work.
- Clears map pins, routes, queues, and local playback state.
- Keeps the app available for a fresh run.

## 3. Manual Driver And Order Pinning

Manual pinning is the clearest proof that the dashboard is not self-solving locally.

Driver pin creates:

- Driver ID.
- Current latitude/longitude.
- Online/available state.
- Initial route state from backend after assignment.

Order pin creates:

- Order ID.
- Pickup coordinate.
- Dropoff coordinate.
- Deadline/SLA metadata.
- Buffer state: waiting, assigned, picked, delivered.

Expected behavior:

- Pinned orders appear in backend buffer before assignment.
- Backend returns assigned driver and final stop sequence.
- FE draws route geometry using OSRM according to backend stop order.
- FE must not invent final assignment if backend is reachable.

## 4. Auto Order And Auto Driver

Auto features are optional load generators.

- `Auto Order OFF` by default: no order spam when live starts.
- `Auto Driver OFF` by default: no driver spam when live starts.
- Turning Auto Order ON adds realistic nearby/randomized orders.
- Turning Auto Driver ON adds a controlled number of drivers, then slows down when enough drivers exist.
- Auto events still go through backend live APIs like manual pins.

Good presentation setup:

```text
Start Live -> manually add 3 drivers -> add 5 orders -> enable Auto Order -> enable Auto Driver only if buffer grows too much.
```

## 5. Demo Scenario

Demo mode uses fixed scenarios for repeatable presentation.

Recommended flow:

1. Open Demo Builder.
2. Pick a scenario.
3. Press `Start Demo`.
4. Demo injects drivers/orders into the same live pipeline.
5. Drivers move like live mode.
6. Pickup/dropoff pins disappear only after completion.
7. Logs show each phase: order stream, buffer, filtering, clustering, candidate matching, seed race, IRX refinement, freeze, insertion, SSE/event stream, KPI.

Use multiple scenarios to demonstrate different routing patterns:

- Dense urban orders.
- Corridor/cross-district orders.
- Sparse long-distance orders.
- Driver shortage.
- Urgent late-risk insertion.
- Stress mode with larger order stream.

## 6. Benchmark Tab

Benchmark mode compares solver strategies on the same dataset.

Expected table rows:

- `IRX`: final route after seed race and IRX optimization.
- `VROOM`: VROOM seed/baseline.
- `ORTOOLS`: OR-Tools baseline.
- `PYVRP`: PyVRP seed/baseline when runtime is available.
- `NEAREST`: nearest-order greedy baseline.
- `ONE_BY_ONE`: one-driver/one-order style baseline.

Important columns:

- Runtime: backend measured solve time.
- Distance: OSRM road distance, not straight-line distance unless explicitly marked fallback.
- Late: number of orders delivered after SLA deadline.
- Coverage: percentage of orders served.
- Sequence: compact pickup/dropoff order, for example `P1-P2-D2-D1`.
- Result/Reason: completed, skipped, rollback, runtime missing, or guard rejection.

## 7. Decision Trace

Use trace for technical explanation.

Show only high-signal stages:

- Input normalization.
- Seed Race.
- Interleaved pickup/dropoff candidate.
- IRX Ensemble Refinement.
- Dominance Guard.
- Final Route.

Useful trace details:

- Selected seed source.
- Selected optimizer.
- Before/after distance.
- Late count before/after.
- Coverage.
- Route churn.
- Runtime budget.
- Guard reason if a candidate is rejected.

## 8. API Sandbox

Use API Sandbox when explaining that this is an API-first Java dispatch system.

Show these calls:

- `GET /v1/health`
- `POST /v1/dispatch/jobs`
- `POST /v1/compare/jobs`
- `POST /v1/live/sessions`
- `POST /v1/live/sessions/{id}/orders`
- `POST /v1/live/sessions/{id}/cycles`
- `GET /v1/live/sessions/{id}/state`

Use collapsed JSON blocks by default, expand only when explaining payload fields.

## 9. Presentation Checklist

Before demo:

- Backend running.
- Dashboard running.
- OSRM configured if real-road routing is required.
- VROOM/PyVRP availability understood; missing runtimes should be described as environment blockers, not algorithm failures.
- Browser zoom 90-100%.
- Console log manual-scroll mode enabled if you want stable screen capture.

During demo:

- Start with a clean map.
- Add drivers before many orders.
- Show buffer before assignment.
- Show backend returned sequence.
- Track one driver to prove live movement.
- End with benchmark + decision trace.
