# Official REST Dispatch API

This document defines the official HTTP boundary for developing IntelligentRouteX as an online dispatch service.

Current implementation:

- Controller: `src/main/java/com/routechain/api/LiveDispatchController.java`
- Health endpoint: `GET /api/v1/dispatch/health`
- Solve endpoint: `POST /api/v1/dispatch/solve`
- Core called by controller: `DispatchV2CompatibleCore.dispatch(...)`
- Core pipeline: `src/main/java/com/routechain/v2/DispatchV2Core.java`

## Development Plan

1. Keep Kafka streaming as the high-throughput production/event channel.
2. Use the REST controller as the official synchronous integration channel for apps, demos, admin tools, and external services.
3. Keep the API schema aligned with `live-dispatch-snapshot/v1` and `live-dispatch-solver-response/v1`.
4. Add production hardening next: authentication, request idempotency, rate limits, P99 latency metrics, and active route lock enforcement.
5. Do not call VROOM, BKS, benchmark artifacts, or comparator outputs inside this production API path.

## Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/dispatch/health` | Lightweight readiness check for the REST dispatch API. |
| `POST` | `/api/v1/dispatch/solve` | Submit one live dispatch snapshot and receive assignments/routes/diagnostics. |

## Input Contract

`POST /api/v1/dispatch/solve` accepts one `live-dispatch-snapshot/v1` object.

### Top-Level Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schemaVersion` | string | yes | Must be `live-dispatch-snapshot/v1`. |
| `snapshotId` | string | yes | Stable id echoed in the response. |
| `timestamp` | ISO-8601 string | yes | Decision timestamp. Offset timestamps like `2026-05-04T11:30:00+07:00` are accepted. |
| `region` | string | yes | Dispatch region key. |
| `mode` | string | no | `shadow`, `canary`, or future `main`. Defaults to `shadow`. |
| `weatherProfile` | string | no | `CLEAR`, `LIGHT_RAIN`, or `HEAVY_RAIN`. If omitted, inferred from `trafficContext`. |
| `nodeIds` | string array | recommended | Ordered node ids used by `durationMatrix`. Required when coordinates are not provided. |
| `nodeCoordinates` | object | optional | Map from node id to `{latitude, longitude}`. |
| `orders` | array | yes | Open orders to assign. |
| `drivers` | array | yes | Available drivers/riders/vehicles. |
| `activeRoutes` | array | yes | Current committed route state. Currently counted in diagnostics; deeper lock enforcement remains a next phase. |
| `durationMatrix` | 2D number array | yes | Travel-time matrix for the snapshot. Currently recorded/validated at API level; the Java V2 core still estimates ETA from points. |
| `trafficContext` | object | yes | Traffic and matrix metadata for audit. |
| `restaurantDelay` | object | yes | Restaurant prep delay estimates. |
| `cancellationRisk` | object | yes | Per-order cancellation risk or risk metadata. |

### Coordinate Policy

The Java core currently uses `GeoPoint` for orders and drivers. The REST API supports two modes:

1. Preferred: provide `nodeCoordinates` or explicit order/driver points.
2. Compatibility: if only `nodeIds` are supplied, the controller creates deterministic synthetic points from node index so benchmark/demo snapshots can run through the API.

Production integrations should provide real coordinates.

### Order Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `orderId` | string | yes | Unique order id. |
| `pickupNodeId` | string | yes | Pickup node id. |
| `dropoffNodeId` | string | yes | Dropoff node id. |
| `restaurantId` | string | recommended | Restaurant/merchant id. |
| `readyTime` | integer minutes | yes | Ready offset from snapshot timestamp. Must be `>= 0`. |
| `dueTime` | integer minutes | yes | Promised completion offset from snapshot timestamp. Must be `> 0`. |
| `serviceTimePickup` | integer minutes | recommended | Pickup service time. |
| `serviceTimeDropoff` | integer minutes | recommended | Dropoff service time. |
| `demand` | integer | recommended | Capacity demand. |
| `priority` | integer | optional | Values `>= 8` map to urgent orders. |
| `pickupPoint` | object | optional | Explicit `{latitude, longitude}`. Overrides `nodeCoordinates`. |
| `dropoffPoint` | object | optional | Explicit `{latitude, longitude}`. Overrides `nodeCoordinates`. |

### Driver Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `driverId` | string | yes | Unique driver id. |
| `startNodeId` | string | yes | Driver start/current node id. |
| `capacity` | integer | recommended | Vehicle capacity. |
| `shiftStart` | integer minutes | recommended | Shift start offset. |
| `shiftEnd` | integer minutes | recommended | Shift end offset. |
| `skills` | string array | optional | Driver skill tags. |
| `currentLoad` | integer | optional | Current load. |
| `maxTasks` | integer | optional | Maximum task count. |
| `endNodeId` | string | optional | End depot/node id. |
| `openRouteAllowed` | boolean | optional | Whether driver can end away from depot. |
| `currentLocation` | object | optional | Explicit `{latitude, longitude}`. Overrides `nodeCoordinates`. |

## Example Request

```json
{
  "schemaVersion": "live-dispatch-snapshot/v1",
  "snapshotId": "lunch-peak-001",
  "timestamp": "2026-05-04T11:30:00+07:00",
  "region": "hcm-district-1",
  "mode": "shadow",
  "nodeIds": ["depot", "restaurant-a", "customer-a"],
  "nodeCoordinates": {
    "depot": {"latitude": 10.7700, "longitude": 106.6950},
    "restaurant-a": {"latitude": 10.7710, "longitude": 106.6960},
    "customer-a": {"latitude": 10.7750, "longitude": 106.7000}
  },
  "orders": [
    {
      "orderId": "order-001",
      "pickupNodeId": "restaurant-a",
      "dropoffNodeId": "customer-a",
      "restaurantId": "restaurant-a",
      "readyTime": 5,
      "dueTime": 45,
      "serviceTimePickup": 2,
      "serviceTimeDropoff": 1,
      "demand": 1,
      "priority": 5
    }
  ],
  "drivers": [
    {
      "driverId": "driver-1",
      "startNodeId": "depot",
      "capacity": 2,
      "shiftStart": 0,
      "shiftEnd": 120,
      "openRouteAllowed": true
    }
  ],
  "activeRoutes": [],
  "durationMatrix": [[0, 8, 18], [8, 0, 10], [18, 10, 0]],
  "trafficContext": {"trafficMode": "normal", "matrixSource": "live", "confidence": 0.95},
  "restaurantDelay": {"restaurant-a": 0},
  "cancellationRisk": {"order-001": 0.08}
}
```

## Output Contract

The API returns one `live-dispatch-solver-response/v1` object.

### Top-Level Response Fields

| Field | Type | Meaning |
|---|---|---|
| `schemaVersion` | string | Always `live-dispatch-solver-response/v1`. |
| `snapshotId` | string | Echoed snapshot id. |
| `solver` | string | Current solver id: `dispatch-v2-compatible-core`. |
| `mode` | string | Echoed/default execution mode. |
| `assignments` | array | Selected driver/order assignments. |
| `routeSequences` | array | Per-driver route stop sequence. |
| `acceptedOrders` | string array | Orders included in assignments. |
| `rejectedOrders` | array | Orders not assigned, with reason. |
| `fallbackReason` | string/null | Set when fallback or validation failure occurs. |
| `runtimeMs` | number | Controller wall-clock runtime. |
| `violations` | array | Request validation or future checker violations. |
| `diagnostics` | object | Trace id, counts, stages, latency summary, selector summary, execution summary, degrade reasons. |

### Assignment Fields

| Field | Meaning |
|---|---|
| `assignmentId` | Internal assignment id. |
| `driverId` | Assigned driver. |
| `orderIds` | Orders covered by this assignment. |
| `pickupEtaMinutes` | Projected pickup ETA. |
| `dropoffEtaMinutes` | Projected completion/dropoff ETA. |
| `selectionRank` | Rank from global selector. |
| `selectionScore` | Selection score. |
| `robustUtility` | Robust utility under scenario scoring. |
| `reasons` | Selection reasons. |
| `degradeReasons` | Degrade/fallback reasons attached to assignment. |

### Route Sequence Fields

| Field | Meaning |
|---|---|
| `driverId` | Driver id. |
| `assignmentId` | Assignment id. |
| `stops` | Ordered pickup/dropoff stop ids emitted by V2 executor. |
| `projectedCompletionEtaMinutes` | Projected completion ETA. |
| `routeSource` | Source of route proposal. |

### Example Error Response

Invalid requests return HTTP `400` with structured body:

```json
{
  "schemaVersion": "live-dispatch-solver-response/v1",
  "snapshotId": "snapshot-1",
  "solver": "dispatch-v2-compatible-core",
  "mode": "shadow",
  "assignments": [],
  "routeSequences": [],
  "acceptedOrders": [],
  "rejectedOrders": [],
  "fallbackReason": "invalid-request",
  "runtimeMs": 1,
  "violations": [
    {"type": "request-validation", "message": "schemaVersion must be live-dispatch-snapshot/v1", "severity": "hard"}
  ],
  "diagnostics": {"accepted": false}
}
```

## Run Locally

```powershell
.\gradlew.bat bootRun --args='--spring.profiles.active=dispatch-v2-prod'
```

Health check:

```powershell
curl.exe http://localhost:8080/api/v1/dispatch/health
```

Solve:

```powershell
curl.exe -X POST http://localhost:8080/api/v1/dispatch/solve `
  -H "Content-Type: application/json" `
  --data-binary "@benchmarks/live_snapshots/demo_v1/lunch_peak_live_snapshot.json"
```

## Relation to Kafka

REST and Kafka call the same core solver path.

| Channel | Input | Output | Use case |
|---|---|---|---|
| REST | `POST /api/v1/dispatch/solve` | HTTP JSON response | Apps, demos, admin tools, synchronous external integration. |
| Kafka | `irx.dispatch.requests.v1` | `irx.dispatch.results.v1` | High-throughput streaming and production event pipeline. |
| Kafka DLQ | invalid/failed envelope | `irx.dispatch.dlq.v1` | Operational failure capture. |

## Next Required Production Hardening

1. Add authentication and tenant/region authorization.
2. Add idempotency using `snapshotId` and request hash.
3. Enforce active route locks from `activeRoutes` in the Java V2 production path.
4. Use `durationMatrix` directly for ETA when supplied, instead of synthetic/geo fallback.
5. Add response hard-constraint checker output to `violations`.
6. Add P95/P99 latency metrics and request/response audit store.
7. Add OpenAPI generation for this contract.
