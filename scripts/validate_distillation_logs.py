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


def iter_rows(path: Path):
    for file in sorted(path.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def family_dirs(bronze_root: Path) -> dict[str, Path]:
    return {child.name: child for child in bronze_root.iterdir() if child.is_dir()}


def validate(bronze_root: Path) -> dict:
    dirs = family_dirs(bronze_root)
    missing = [family for family in REQUIRED_FAMILIES if family not in dirs]
    if missing:
        raise ValueError(f"Missing Bronze families: {missing}")
    counts: dict[str, int] = {}
    leakage_errors: list[str] = []
    candidate_rows = 0
    for family, directory in dirs.items():
        count = 0
        for row in iter_rows(directory):
            count += 1
            row_type = row.get("rowType")
            if row_type == "candidate":
                candidate_rows += 1
                if not row.get("candidateId"):
                    raise ValueError(f"Candidate row missing candidateId in {family}")
                if not row.get("entityType") or not row.get("entityId"):
                    raise ValueError(f"Candidate row missing entity identity in {family}")
            observation_time = row.get("observationTime")
            decision_time = row.get("decisionTime")
            outcome_time = row.get("outcomeTime")
            populated = sum(bool(value) for value in (observation_time, decision_time, outcome_time))
            if populated > 1:
                raise ValueError(f"Row has multiple time layers in {family}")
            if family in {"decision-stage-input", "decision-stage-output", "decision-stage-join"}:
                forbidden = OUTCOME_FIELDS.intersection(row.keys())
                if forbidden:
                    leakage_errors.append(f"{family} contains outcome fields {sorted(forbidden)}")
        counts[family] = count
    if candidate_rows == 0:
        raise ValueError("No candidate rows found in Bronze")
    if leakage_errors:
        raise ValueError("; ".join(leakage_errors))
    return {"counts": counts, "candidateRows": candidate_rows}


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
