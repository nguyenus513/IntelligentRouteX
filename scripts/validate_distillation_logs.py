from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_FAMILIES = (
    "harvest-run-manifest",
    "decision-stage-input",
    "decision-stage-output",
    "decision-stage-join",
    "dispatch-execution",
    "dispatch-outcome",
    "geo-tile-selection-trace",
    "tile-feature-trace",
    "bundle-geometry-trace",
    "driver-pickup-fit-trace",
    "route-vector-trace",
    "route-stop-trace",
    "traffic-context-trace",
    "tabular-teacher-trace",
    "greedrl-teacher-trace",
    "routefinder-teacher-trace",
    "forecast-teacher-trace",
)

REQUIRED_TOP_LEVEL_FIELDS = (
    "schemaVersion",
    "rowType",
    "timeLayer",
    "antiLeakageClass",
    "traceId",
    "runId",
    "stageName",
    "entityType",
    "entityId",
)

ALLOWED_ROW_TYPES = {"stage", "candidate", "summary", "outcome"}
ALLOWED_TIME_LAYERS = {"observation", "teacher", "outcome"}
OUTCOME_FIELDS = {
    "actualPickupTravelTimeSeconds",
    "actualMerchantWaitTimeSeconds",
    "actualDropoffTravelTimeSeconds",
    "totalCompletionTimeSeconds",
    "realizedTrafficDelaySeconds",
    "realizedWeatherModifier",
    "delivered",
    "labelQuality",
}
GEO_REQUIRED_FIELDS = (
    "pickupLat",
    "pickupLng",
    "dropLat",
    "dropLng",
    "bundleCentroidLat",
    "bundleCentroidLng",
)
PROVENANCE_REQUIRED_FAMILIES = {
    "geo-tile-selection-trace",
    "tile-feature-trace",
    "bundle-geometry-trace",
    "driver-pickup-fit-trace",
    "route-vector-trace",
    "route-stop-trace",
    "traffic-context-trace",
    "tabular-teacher-trace",
    "greedrl-teacher-trace",
    "routefinder-teacher-trace",
    "forecast-teacher-trace",
    "dispatch-outcome",
}
GEOSPATIAL_COVERAGE_THRESHOLD = 0.95


def iter_rows(path: Path):
    for file in sorted(path.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def family_dirs(bronze_root: Path) -> dict[str, Path]:
    return {child.name: child for child in bronze_root.iterdir() if child.is_dir()}


def populated_time_fields(row: dict) -> list[str]:
    fields = []
    for name in ("observationTime", "decisionTime", "outcomeTime"):
        if row.get(name):
            fields.append(name)
    return fields


def validate(bronze_root: Path) -> dict:
    dirs = family_dirs(bronze_root)
    missing = [family for family in REQUIRED_FAMILIES if family not in dirs]
    if missing:
        raise ValueError(f"Missing Bronze families: {missing}")

    counts: dict[str, int] = {}
    leakage_errors: list[str] = []
    candidate_rows = 0
    candidate_identity_coverage = 0
    geo_candidate_rows = 0
    geo_complete_rows = 0

    for family, directory in dirs.items():
        count = 0
        for row in iter_rows(directory):
            count += 1
            for field in REQUIRED_TOP_LEVEL_FIELDS:
                if field not in row:
                    raise ValueError(f"Row missing top-level field '{field}' in {family}")
            if row.get("rowType") not in ALLOWED_ROW_TYPES:
                raise ValueError(f"Row has invalid rowType in {family}: {row.get('rowType')}")
            if row.get("timeLayer") not in ALLOWED_TIME_LAYERS:
                raise ValueError(f"Row has invalid timeLayer in {family}: {row.get('timeLayer')}")
            populated = populated_time_fields(row)
            if len(populated) != 1:
                raise ValueError(f"Row must populate exactly one time field in {family}")
            expected_time = {
                "observation": "observationTime",
                "teacher": "decisionTime",
                "outcome": "outcomeTime",
            }[row["timeLayer"]]
            if populated[0] != expected_time:
                raise ValueError(f"Row timeLayer does not match populated timestamp in {family}")

            if family in PROVENANCE_REQUIRED_FAMILIES:
                for provenance_field in ("source", "fallbackUsed", "missingReason"):
                    if provenance_field not in row:
                        raise ValueError(f"{family} row missing provenance field '{provenance_field}'")

            if row.get("rowType") == "candidate":
                candidate_rows += 1
                if row.get("candidateId") and row.get("entityType") and row.get("entityId"):
                    candidate_identity_coverage += 1
                else:
                    raise ValueError(f"Candidate row missing stable identity in {family}")

            if family in {"decision-stage-input", "decision-stage-output", "decision-stage-join"}:
                forbidden = OUTCOME_FIELDS.intersection(row.keys())
                if forbidden:
                    leakage_errors.append(f"{family} contains outcome fields {sorted(forbidden)}")

            if family == "decision-stage-input" and row.get("rowType") == "candidate":
                geo_candidate_rows += 1
                if all(field in row for field in GEO_REQUIRED_FIELDS):
                    geo_complete_rows += 1
        counts[family] = count

    if candidate_rows == 0:
        raise ValueError("No candidate rows found in Bronze")
    if leakage_errors:
        raise ValueError("; ".join(leakage_errors))

    geo_coverage = 1.0 if geo_candidate_rows == 0 else geo_complete_rows / geo_candidate_rows
    if geo_coverage < GEOSPATIAL_COVERAGE_THRESHOLD:
        raise ValueError(f"Geospatial coverage below threshold: {geo_coverage:.3f}")

    return {
        "schemaVersion": "dispatch-v2-harvest-validation-report/v2",
        "counts": counts,
        "candidateRows": candidate_rows,
        "coverage": {
            "candidateIdentityCoverage": candidate_identity_coverage / candidate_rows,
            "geospatialCoverage": geo_coverage,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Bronze distillation logs.")
    parser.add_argument("--bronze-root", required=True)
    args = parser.parse_args(argv)
    bronze_root = Path(args.bronze_root)
    report = validate(bronze_root)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
