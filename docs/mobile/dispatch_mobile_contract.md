# Mobile Dispatch Contract

## Principle

Mobile apps never choose drivers or optimize routes. They only submit state changes and render assignment state produced by IntelligentRouteX through Firebase.

## Callable Function Inputs

### `createUserOrder`

```json
{
  "restaurantId": "r1",
  "items": [{"itemId": "m1", "quantity": 2}],
  "dropoffLocation": {"lat": 10.78, "lng": 106.70},
  "dropoffAddress": "Saigon Pearl lobby",
  "paymentMethod": "cash",
  "note": "Call at lobby"
}
```

Writes `orders/{orderId}` with `status = ORDER_CREATED`.

### `setDriverOnline`

```json
{
  "online": true,
  "location": {"lat": 10.776, "lng": 106.704},
  "capacity": 2,
  "vehicleType": "bike"
}
```

Writes `drivers/{driverId}` and `driver_locations/{driverId}`.

### `updateDriverLocation`

```json
{
  "location": {"lat": 10.776, "lng": 106.704},
  "heading": 82,
  "speed": 7.2,
  "accuracy": 9,
  "assignmentId": "a123"
}
```

Writes RTDB `driver_locations/{driverId}` and `order_tracking/{orderId}` when assigned.

## Dispatch Request

Cloud Functions calls `POST /api/dispatch/v2`:

```json
{
  "schemaVersion": "dispatch-v2-request/v1",
  "traceId": "firebase-o1-1710000000000",
  "openOrders": [
    {
      "orderId": "o1",
      "pickupPoint": {"latitude": 10.7741, "longitude": 106.7038},
      "dropoffPoint": {"latitude": 10.7942, "longitude": 106.7218},
      "createdAt": "2026-05-06T00:00:00Z",
      "readyAt": "2026-05-06T00:08:00Z",
      "promisedEtaMinutes": 35,
      "urgent": false
    }
  ],
  "availableDrivers": [
    {
      "driverId": "d1",
      "currentLocation": {"latitude": 10.776, "longitude": 106.704},
      "capacity": 2,
      "status": "idle"
    }
  ],
  "regions": [{"regionId": "hcm", "name": "Ho Chi Minh City"}],
  "weatherProfile": "LIGHT_RAIN",
  "decisionTime": "2026-05-06T00:00:05Z"
}
```

## Dispatch Result Fields Used By Mobile

The Android apps consume the Firebase assignment document, not the raw engine response. Functions must map engine response into this stable shape:

```json
{
  "assignmentId": "a123",
  "driverId": "d1",
  "driverUid": "d1",
  "status": "assigned",
  "orderIds": ["o1", "o2"],
  "pickupSequence": ["r1", "r2"],
  "dropoffSequence": ["o1", "o2"],
  "routePlan": {
    "schemaVersion": "mobile-route-plan/v1",
    "sequence": [
      {"sequence": 1, "type": "pickup", "refId": "r1", "orderId": "o1"},
      {"sequence": 2, "type": "pickup", "refId": "r2", "orderId": "o2"},
      {"sequence": 3, "type": "dropoff", "refId": "o1", "orderId": "o1"},
      {"sequence": 4, "type": "dropoff", "refId": "o2", "orderId": "o2"}
    ],
    "legs": [
      {
        "sequence": 1,
        "fromStopId": "driver:d1",
        "toStopId": "pickup:o1",
        "distanceMeters": 1800,
        "etaSeconds": 420,
        "geometryKind": "encoded-polyline",
        "polyline": "..."
      }
    ],
    "distanceMeters": 8200,
    "etaSeconds": 1840,
    "encodedPolyline": "..."
  },
  "dispatch": {
    "engine": "IntelligentRouteX",
    "traceId": "firebase-o1-1710000000000",
    "fallback": false,
    "objectiveScore": 0.82,
    "confidence": 0.88,
    "degradeReasons": []
  }
}
```

## Status Transitions

```text
ORDER_CREATED
ASSIGNING_DRIVER
DRIVER_ASSIGNED
DRIVER_TO_RESTAURANT
ARRIVED_AT_RESTAURANT
PICKED_UP
DRIVER_TO_USER
ARRIVED_AT_USER
DELIVERED
CANCELLED
```

Batch assignments repeat pickup/dropoff substates per stop but keep one assignment id.

## Mobile Rendering Requirements

Driver assignment card:

- Shows order count, payout, total ETA, total distance, risk, and countdown.
- Shows `routePlan.sequence` as `P1 -> P2 -> D1 -> D2`.
- Accept/reject calls Functions only.

Driver navigation:

- Draws active leg with full opacity and remaining legs muted.
- CTA text is derived from current sequence item.
- Completion calls `driverAdvanceAssignment` with the next allowed status.

User tracking:

- Reads `orders/{orderId}`, `order_tracking/{orderId}`, and `assignments/{assignmentId}.routePlan`.
- Draws restaurant, driver, user marker, route polyline, status timeline, ETA, and support actions.
