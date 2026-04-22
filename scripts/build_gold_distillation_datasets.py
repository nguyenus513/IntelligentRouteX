from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_unified_rows(silver_root: Path) -> list[dict]:
    joins = read_jsonl(silver_root / "decision_stage_join.jsonl")
    outcomes = read_jsonl(silver_root / "dispatch_outcomes.jsonl")
    outcome_by_trace = {row.get("traceId"): row for row in outcomes if row.get("traceId")}
    rows = []
    for row in joins:
        merged = dict(row)
        merged.update(outcome_by_trace.get(row.get("traceId"), {}))
        rows.append(merged)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Gold parquet datasets from Silver JSONL.")
    parser.add_argument("--silver-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    silver_root = Path(args.silver_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    unified_rows = build_unified_rows(silver_root)
    unified_table = pa.Table.from_pylist(unified_rows)
    pq.write_table(unified_table, output_dir / "unified_dispatch_distillation.parquet")

    selection_rows = []
    for row in unified_rows:
        selection_rows.append({
            "traceId": row.get("traceId"),
            "stageName": row.get("stageName"),
            "candidateId": row.get("candidateId"),
            "selected": row.get("selected"),
            "downstreamChosen": row.get("downstreamChosen"),
            "score": row.get("score"),
            "rank": row.get("rank"),
            "confidence": row.get("confidence"),
        })
    pq.write_table(pa.Table.from_pylist(selection_rows), output_dir / "selection_score.parquet")

    manifest = {
        "schemaVersion": "dispatch-v2-gold-manifest/v1",
        "silverRoot": str(silver_root),
        "unifiedRows": len(unified_rows),
        "selectionRows": len(selection_rows),
    }
    (output_dir / "gold_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
