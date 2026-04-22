from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


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


def normalize(bronze_root: Path) -> dict[str, list[dict]]:
    inputs_by_key: dict[tuple[str, str, str], dict] = {}
    outputs_by_key: dict[tuple[str, str, str], dict] = {}
    joins: list[dict] = []
    for row in iter_family_rows(bronze_root, "decision-stage-input") or []:
        if row.get("rowType") == "candidate":
            key = (row.get("traceId", ""), row.get("stageName", ""), row.get("candidateId", ""))
            inputs_by_key[key] = row
    for row in iter_family_rows(bronze_root, "decision-stage-output") or []:
        if row.get("rowType") == "candidate":
            key = (row.get("traceId", ""), row.get("stageName", ""), row.get("candidateId", ""))
            outputs_by_key[key] = row
    for row in iter_family_rows(bronze_root, "decision-stage-join") or []:
        if row.get("rowType") != "candidate":
            continue
        key = (row.get("traceId", ""), row.get("stageName", ""), row.get("candidateId", ""))
        merged = {}
        merged.update(inputs_by_key.get(key, {}))
        merged.update(outputs_by_key.get(key, {}))
        merged.update(row)
        joins.append(merged)

    route_vectors = list(iter_family_rows(bronze_root, "route-vector-trace") or [])
    route_stops = list(iter_family_rows(bronze_root, "route-stop-trace") or [])
    outcomes = list(iter_family_rows(bronze_root, "dispatch-outcome") or [])
    teachers = []
    for family in ("tabular-teacher-trace", "greedrl-teacher-trace", "routefinder-teacher-trace", "forecast-teacher-trace"):
        teachers.extend(iter_family_rows(bronze_root, family) or [])
    return {
        "decision_stage_join": joins,
        "route_vectors": route_vectors,
        "route_stops": route_stops,
        "dispatch_outcomes": outcomes,
        "teacher_traces": teachers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Silver datasets from Bronze JSONL.")
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
        "schemaVersion": "dispatch-v2-silver-manifest/v1",
        "bronzeRoot": str(bronze_root),
        "counts": {name: len(entries) for name, entries in rows.items()},
    }
    (output_dir / "silver_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
