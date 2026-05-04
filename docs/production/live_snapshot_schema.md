# Phase 78 Live Dispatch Snapshot Schema

This schema defines the production input contract for running IntelligentRouteX in shadow mode or future controlled dispatch integration.

The current system is **not** `PRODUCTION_MAIN_READY`. This schema is a prerequisite for live adapter work, fallback policies, replay logs, and SLA monitoring.

## Required Top-Level Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schemaVersion` | string | yes | Use `live-dispatch-snapshot/v1`. |
| `snapshotId` | string | yes | Stable unique id for replay/debug. |
| `timestamp` | string | yes | ISO-8601 snapshot creation time. |
| `region` | string | yes | Dispatch region/city/zone. |
| `orders` | array | yes | Open orders to assign or preserve. |
| `drivers` | array | yes | Available drivers/riders/vehicles. |
| `activeRoutes` | array | yes | Current committed route state. Empty array is allowed. |
| `durationMatrix` | 2D number array | yes | Travel-time matrix used for SLA/time-window validation. |
| `trafficContext` | object | yes | Traffic/rain/peak metadata for audit. |
| `restaurantDelay` | object | yes | Per-restaurant prep delay estimates. |
| `cancellationRisk` | object | yes | Per-order cancellation risk or risk model metadata. |

## Order Fields

Required per order:

- `orderId`
- `pickupNodeId`
- `dropoffNodeId`
- `restaurantId`
- `readyTime`
- `dueTime`
- `serviceTimePickup`
- `serviceTimeDropoff`
- `demand`

Optional but recommended:

- `priority`
- `requiredSkills`
- `cancellationRisk`
- `promisedDeliveryTime`

## Driver Fields

Required per driver:

- `driverId`
- `startNodeId`
- `capacity`
- `shiftStart`
- `shiftEnd`

Optional but recommended:

- `skills`
- `breaks`
- `currentLoad`
- `maxTasks`
- `endNodeId`
- `openRouteAllowed`

## Active Route Fields

Required per active route:

- `driverId`
- `route`
- `lockedPrefixLength`

`activeRoutes` is mandatory even when empty. This prevents accidentally optimizing as if no committed dispatch state exists.

## Matrix Contract

- `durationMatrix` must be square.
- Every node referenced by orders, drivers, and active routes must have an index in `nodeIdToMatrixIndex` if that map is supplied.
- Production comparisons must not use distance as duration unless explicitly recorded in `trafficContext.durationSource`.

## Minimal Example

```json
{
  "schemaVersion": "live-dispatch-snapshot/v1",
  "snapshotId": "demo-001",
  "timestamp": "2026-05-04T13:30:00+07:00",
  "region": "hcm-demo",
  "orders": [],
  "drivers": [],
  "activeRoutes": [],
  "durationMatrix": [[0]],
  "trafficContext": {"durationSource": "synthetic"},
  "restaurantDelay": {},
  "cancellationRisk": {}
}
```
