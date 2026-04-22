GLOBAL PACK: output_contract

- Output must match `stage_output_v1`.
- Always return `selectedIds`.
- Always return `assessments.summary`, `assessments.reasonCodes`, and `assessments.items`.
- Every assessment item must include:
  - `id`
  - `score`
  - `rank`
  - `selected`
  - `confidence`
  - `reasonCodes`
  - `dominanceReasonCodes`
  - `regretToBestAlternative`
  - `driverFitSummary`
  - `routeVectorRefs`
  - `geospatialFlags`
  - `burstSensitivityFlags`
  - `rationale`
