# Active Route Locking Policy

Active route locking protects already committed dispatch work when a new live snapshot is optimized.

## Policy

When `--enforce-active-route-locking` is enabled, every `activeRoutes` entry is treated as a committed route prefix.

The solver output must preserve:

- every locked node;
- locked node order;
- no duplicate locked node;
- the same driver assignment when route driver metadata is available;
- insertion only after the locked prefix.

## Fallback

If a candidate solution violates the locked prefix policy, Phase 79 applies fallback with reason `active-route-lock-violation`.

This is intentionally conservative because reordering an already committed pickup/dropoff can break driver UX, customer promises, and restaurant pickup coordination.

## Metrics

Phase 79 records:

- `lockedPrefixPreservedCount`
- `lockedPrefixViolationCount`
- `changedActiveRouteCount`
- `insertedAfterLockedPrefixCount`
- `routeChurnScore`

## Production Readiness

Active route locking removes one Phase 79 bridge limitation, but it does not claim `PRODUCTION_MAIN_READY`. Production-main still requires live adapter wiring, fallback execution, replay/canary evidence, monitoring, alerting, and SLA dashboards.
