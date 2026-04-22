# Dispatch V2 Bronze Schema V1

Bronze is append-only training raw. It must not change replay semantics or reconstruct facts from downstream outcomes.

## Required Envelope Fields

Every Bronze row must carry:

- `schemaVersion`
- `rowType`: `stage | candidate | summary | outcome`
- `timeLayer`: `observation | teacher | outcome`
- `antiLeakageClass`: `METADATA_ONLY | DECISION_SAFE | TEACHER_DECISION | OUTCOME_ONLY`
- `traceId`
- `runId`
- `tickId`
- `stageName`
- `entityType`
- `entityId`
- `candidateId` for every candidate row
- exactly one populated timestamp field:
  - `observationTime`
  - `decisionTime`
  - `outcomeTime`

## Identity And Units

- Candidate ids are stable and normalized:
  - `bundle:<bundleId>`
  - `anchor:<bundleId>:<anchorOrderId>`
  - `driver:<bundleId>:<driverId>`
  - `proposal:<proposalId>`
  - `assignment:<assignmentId>`
  - `observation:<entityId>`
- Coordinates are decimal lat/lng.
- Distances are meters.
- Durations are seconds.
- Timestamps are UTC ISO-8601.

## Provenance Rule

Every family with estimated, fallback, or missing geo/traffic/weather/teacher data must carry:

- `source`
- `fallbackUsed`
- `missingReason`

Additional source fields are family-specific:

- `trafficSource`
- `weatherSource`
- `tileSource`
- `teacherSource`

## Family Contracts

- `harvest-run-manifest`: `rowType=stage`, `timeLayer=teacher`, metadata only.
- `decision-stage-input`: stage and candidate rows, `timeLayer=observation`, no outcome fields.
- `decision-stage-output`: stage and candidate rows, `timeLayer=teacher`, includes rank/score/reason fields.
- `decision-stage-join`: candidate rows, `timeLayer=teacher`, includes selected/non-selected/downstream labels.
- `dispatch-execution`: stage rows, `timeLayer=teacher`, execution facts only.
- `dispatch-outcome`: outcome rows, `timeLayer=outcome`, realized labels only.
- `geo-tile-selection-trace`: candidate rows, `timeLayer=observation`, no raw tile imagery.
- `tile-feature-trace`: candidate rows, `timeLayer=observation`, compressed tile vectors only.
- `bundle-geometry-trace`: candidate rows, `timeLayer=observation`.
- `driver-pickup-fit-trace`: candidate rows, `timeLayer=observation`.
- `route-vector-trace`: summary rows, `timeLayer=observation`.
- `route-stop-trace`: candidate rows, `timeLayer=observation`.
- `traffic-context-trace`: candidate rows, `timeLayer=observation`.
- `tabular-teacher-trace`, `greedrl-teacher-trace`, `routefinder-teacher-trace`, `forecast-teacher-trace`: candidate rows, `timeLayer=teacher`.
