from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


DECISION_TIME_FORBIDDEN_FIELDS = {
    "actualPickupTravelTimeSeconds",
    "actualMerchantWaitTimeSeconds",
    "actualDropoffTravelTimeSeconds",
    "totalCompletionTimeSeconds",
    "realizedTrafficDelaySeconds",
    "realizedWeatherModifier",
    "delivered",
    "labelQuality",
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("traceId", "")),
        str(row.get("stageName", "")),
        str(row.get("candidateId", "")),
    )


def group_latest(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = canonical_key(row)
        if all(key):
            grouped[key] = row
    return grouped


def build_unified_rows(silver_root: Path) -> list[dict]:
    joins = read_jsonl(silver_root / "decision_stage_join_canonical.jsonl")
    route_candidates = group_latest(read_jsonl(silver_root / "route_candidate_canonical.jsonl"))
    driver_fit = group_latest(read_jsonl(silver_root / "driver_fit_canonical.jsonl"))
    bundle_geometry = group_latest(read_jsonl(silver_root / "bundle_geometry_canonical.jsonl"))
    tile_context = group_latest(read_jsonl(silver_root / "tile_context_canonical.jsonl"))
    outcomes = read_jsonl(silver_root / "dispatch_outcome_canonical.jsonl")
    outcome_by_trace = {str(row.get("traceId")): row for row in outcomes if row.get("traceId")}

    teacher_rows = read_jsonl(silver_root / "teacher_trace_canonical.jsonl")
    teachers_by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in teacher_rows:
        key = canonical_key(row)
        if all(key):
            teachers_by_key[key].append(row)

    rows = []
    for row in joins:
        merged = dict(row)
        key = canonical_key(row)
        for source_row in (
            route_candidates.get(key),
            driver_fit.get(key),
            bundle_geometry.get(key),
            tile_context.get(key),
        ):
            if source_row:
                merged.update(source_row)
        teacher_group = teachers_by_key.get(key, [])
        merged["teacherTraceCount"] = len(teacher_group)
        merged["teacherKinds"] = sorted({str(item.get("teacherKind", "")) for item in teacher_group if item.get("teacherKind")})
        merged["teacherAppliedCount"] = sum(1 for item in teacher_group if item.get("applied"))
        merged["teacherFallbackUsed"] = any(bool(item.get("fallbackUsed")) for item in teacher_group)
        merged["teacherFingerprints"] = sorted({str(item.get("fingerprint", "")) for item in teacher_group if item.get("fingerprint")})
        outcome = outcome_by_trace.get(str(row.get("traceId")))
        if outcome:
            merged.update(outcome)
        rows.append(merged)
    return rows


def build_selection_rows(unified_rows: list[dict]) -> list[dict]:
    rows = []
    for row in unified_rows:
        rows.append({
            "traceId": row.get("traceId"),
            "runId": row.get("runId"),
            "tickId": row.get("tickId"),
            "stageName": row.get("stageName"),
            "candidateId": row.get("candidateId"),
            "entityType": row.get("entityType"),
            "entityId": row.get("entityId"),
            "selected": row.get("selected"),
            "downstreamChosen": row.get("downstreamChosen"),
            "score": row.get("score"),
            "rank": row.get("rank"),
            "confidence": row.get("confidence"),
            "timeLayer": row.get("timeLayer"),
            "antiLeakageClass": row.get("antiLeakageClass"),
            "source": row.get("source"),
            "fallbackUsed": row.get("fallbackUsed"),
            "missingReason": row.get("missingReason"),
            "teacherTraceCount": row.get("teacherTraceCount"),
            "teacherFallbackUsed": row.get("teacherFallbackUsed"),
            "labelQuality": row.get("labelQuality"),
        })
    return rows


def validate_decision_time_columns(unified_rows: list[dict]) -> None:
    for row in unified_rows:
        if row.get("timeLayer") == "outcome":
            continue
        forbidden = DECISION_TIME_FORBIDDEN_FIELDS.intersection(row.keys())
        if forbidden and row.get("labelQuality") is None:
            raise ValueError(f"Decision-time row unexpectedly carries outcome fields without joined outcome labels: {sorted(forbidden)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Gold parquet datasets from Silver canonical JSONL.")
    parser.add_argument("--silver-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    silver_root = Path(args.silver_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    unified_rows = build_unified_rows(silver_root)
    validate_decision_time_columns(unified_rows)
    pq.write_table(pa.Table.from_pylist(unified_rows), output_dir / "unified_dispatch_distillation.parquet")

    selection_rows = build_selection_rows(unified_rows)
    pq.write_table(pa.Table.from_pylist(selection_rows), output_dir / "selection_score.parquet")

    manifest = {
        "schemaVersion": "dispatch-v2-gold-manifest/v2",
        "silverRoot": str(silver_root),
        "unifiedRows": len(unified_rows),
        "selectionRows": len(selection_rows),
        "requiredOutputs": [
            "unified_dispatch_distillation.parquet",
            "selection_score.parquet",
        ],
    }
    (output_dir / "gold_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
