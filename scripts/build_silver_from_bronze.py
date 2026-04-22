from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


CANONICAL_TABLES = (
    "decision_stage_join_canonical",
    "route_candidate_canonical",
    "driver_fit_canonical",
    "bundle_geometry_canonical",
    "tile_context_canonical",
    "teacher_trace_canonical",
    "dispatch_outcome_canonical",
)


def iter_family_rows(bronze_root: Path, family: str):
    directory = bronze_root / family
    if not directory.exists():
        return
    for file in sorted(directory.glob("*.jsonl")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def candidate_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("traceId", "")),
        str(row.get("stageName", "")),
        str(row.get("candidateId", "")),
    )


def family_name_to_teacher_kind(family: str) -> str:
    return family.replace("-teacher-trace", "")


def build_decision_stage_join(bronze_root: Path) -> list[dict]:
    inputs_by_key: dict[tuple[str, str, str], dict] = {}
    outputs_by_key: dict[tuple[str, str, str], dict] = {}
    rows: list[dict] = []
    for row in iter_family_rows(bronze_root, "decision-stage-input") or []:
        if row.get("rowType") == "candidate":
            inputs_by_key[candidate_key(row)] = row
    for row in iter_family_rows(bronze_root, "decision-stage-output") or []:
        if row.get("rowType") == "candidate":
            outputs_by_key[candidate_key(row)] = row
    for row in iter_family_rows(bronze_root, "decision-stage-join") or []:
        if row.get("rowType") != "candidate":
            continue
        key = candidate_key(row)
        merged = {}
        merged.update(inputs_by_key.get(key, {}))
        merged.update(outputs_by_key.get(key, {}))
        merged.update(row)
        merged["canonicalTable"] = "decision_stage_join_canonical"
        rows.append(merged)
    return rows


def build_route_candidate(bronze_root: Path) -> list[dict]:
    summaries: dict[tuple[str, str], dict] = {}
    stops_by_proposal: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in iter_family_rows(bronze_root, "route-vector-trace") or []:
        proposal_id = str(row.get("proposalId", row.get("entityId", "")))
        if proposal_id:
            summaries[(str(row.get("traceId", "")), proposal_id)] = row
    for row in iter_family_rows(bronze_root, "route-stop-trace") or []:
        proposal_id = str(row.get("proposalId", ""))
        if proposal_id:
            stops_by_proposal[(str(row.get("traceId", "")), proposal_id)].append(row)
    rows: list[dict] = []
    for key, summary in summaries.items():
        stops = sorted(stops_by_proposal.get(key, []), key=lambda item: item.get("stopIndex", 0))
        row = dict(summary)
        row["canonicalTable"] = "route_candidate_canonical"
        row["proposalId"] = key[1]
        row["stopCount"] = len(stops)
        row["pickupStopCount"] = sum(1 for stop in stops if str(stop.get("stopType", "")).lower() == "pickup")
        row["dropoffStopCount"] = sum(1 for stop in stops if str(stop.get("stopType", "")).lower() == "dropoff")
        row["routeStopIds"] = [stop.get("orderId") for stop in stops]
        row["routeStopLatLng"] = [[stop.get("lat"), stop.get("lng")] for stop in stops]
        row["routeLegDistanceMeters"] = [stop.get("legDistanceMeters") for stop in stops]
        row["routeLegTravelTimeSeconds"] = [stop.get("legTravelTimeSeconds") for stop in stops]
        rows.append(row)
    return rows


def build_family_passthrough(bronze_root: Path, family: str, table_name: str) -> list[dict]:
    rows: list[dict] = []
    for row in iter_family_rows(bronze_root, family) or []:
        if row.get("rowType") not in {"candidate", "summary", "outcome", "stage"}:
            continue
        entry = dict(row)
        entry["canonicalTable"] = table_name
        rows.append(entry)
    return rows


def build_tile_context(bronze_root: Path) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for family in ("geo-tile-selection-trace", "tile-feature-trace", "traffic-context-trace"):
        for row in iter_family_rows(bronze_root, family) or []:
            candidate_id = str(row.get("candidateId", ""))
            if not candidate_id:
                continue
            key = candidate_key(row)
            entry = grouped.setdefault(key, {
                "traceId": row.get("traceId"),
                "runId": row.get("runId"),
                "tickId": row.get("tickId"),
                "stageName": row.get("stageName"),
                "entityType": row.get("entityType"),
                "entityId": row.get("entityId"),
                "candidateId": candidate_id,
                "rowType": "candidate",
                "timeLayer": row.get("timeLayer"),
                "antiLeakageClass": row.get("antiLeakageClass"),
                "tileSelections": [],
                "tileFeatures": [],
                "trafficContexts": [],
                "canonicalTable": "tile_context_canonical",
            })
            if family == "geo-tile-selection-trace":
                entry["tileSelections"].append(row)
            elif family == "tile-feature-trace":
                entry["tileFeatures"].append(row)
            else:
                entry["trafficContexts"].append(row)
                for field in ("zoneId", "timeBucket", "avgSpeedMps", "jamClass", "trafficSource", "weatherSource"):
                    if field in row:
                        entry[field] = row[field]
    return list(grouped.values())


def build_teacher_trace(bronze_root: Path) -> list[dict]:
    rows: list[dict] = []
    for family in ("tabular-teacher-trace", "greedrl-teacher-trace", "routefinder-teacher-trace", "forecast-teacher-trace"):
        teacher_kind = family_name_to_teacher_kind(family)
        for row in iter_family_rows(bronze_root, family) or []:
            entry = dict(row)
            entry["teacherKind"] = entry.get("teacherFamily", teacher_kind)
            entry["canonicalTable"] = "teacher_trace_canonical"
            rows.append(entry)
    return rows


def normalize(bronze_root: Path) -> dict[str, list[dict]]:
    rows = {
        "decision_stage_join_canonical": build_decision_stage_join(bronze_root),
        "route_candidate_canonical": build_route_candidate(bronze_root),
        "driver_fit_canonical": build_family_passthrough(bronze_root, "driver-pickup-fit-trace", "driver_fit_canonical"),
        "bundle_geometry_canonical": build_family_passthrough(bronze_root, "bundle-geometry-trace", "bundle_geometry_canonical"),
        "tile_context_canonical": build_tile_context(bronze_root),
        "teacher_trace_canonical": build_teacher_trace(bronze_root),
        "dispatch_outcome_canonical": build_family_passthrough(bronze_root, "dispatch-outcome", "dispatch_outcome_canonical"),
    }
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Silver canonical datasets from Bronze JSONL.")
    parser.add_argument("--bronze-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    bronze_root = Path(args.bronze_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = normalize(bronze_root)
    for name, entries in rows.items():
        append_jsonl(output_dir / f"{name}.jsonl", entries)
    manifest = {
        "schemaVersion": "dispatch-v2-silver-manifest/v2",
        "bronzeRoot": str(bronze_root),
        "tables": list(CANONICAL_TABLES),
        "counts": {name: len(entries) for name, entries in rows.items()},
    }
    (output_dir / "silver_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
