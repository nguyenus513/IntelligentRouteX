from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from traffic.phase82_matrix_validator import active_route_traffic_risk, audit_traffic_matrix


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "benchmarks" / "live_snapshots" / "traffic_v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase82_traffic_matrix_audit_v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def traffic_sla_metrics(snapshot: Dict[str, Any], audit: Dict[str, Any], risk: Dict[str, Any]) -> Dict[str, Any]:
    traffic = snapshot.get("trafficContext", {})
    multiplier = float(traffic.get("multiplier", 1.0) or 1.0)
    rows = [float(value) for row in snapshot.get("durationMatrix", []) for value in row if isinstance(value, (int, float)) and value > 0]
    mean_duration = sum(rows) / len(rows) if rows else 0.0
    return {
        "snapshotId": snapshot.get("snapshotId"),
        "trafficAdjustedO2DMean": mean_duration,
        "trafficAdjustedO2DP95": sorted(rows)[min(len(rows) - 1, int(round((len(rows) - 1) * 0.95)))] if rows else 0.0,
        "trafficDelayDeltaMean": mean_duration * max(0.0, multiplier - 1.0),
        "trafficDelayDeltaP95": (sorted(rows)[min(len(rows) - 1, int(round((len(rows) - 1) * 0.95)))] if rows else 0.0) * max(0.0, multiplier - 1.0),
        "matrixFreshnessSeconds": audit.get("freshnessSeconds"),
        "trafficConfidence": audit.get("confidence"),
        "trafficFallbackRate": 1.0 if audit.get("fallbackUsed") else 0.0,
        "activeRouteTrafficRiskCount": risk.get("activeRouteTrafficRiskCount", 0),
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    snapshot_dir = Path(args.snapshot_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    fallback = []
    metrics = []
    for path in sorted(snapshot_dir.glob("*.json")):
        snapshot = read_json(path)
        audit = audit_traffic_matrix(snapshot, args.traffic_max_freshness_seconds, args.traffic_min_confidence, args.require_live_traffic, args.allow_traffic_fallback)
        risk = active_route_traffic_risk(snapshot)
        rows.append({**audit, **risk, "snapshotPath": str(path)})
        fallback.append({"snapshotId": snapshot.get("snapshotId"), "trafficFallbackApplied": bool(audit.get("fallbackRequired") or audit.get("fallbackUsed")), "trafficFallbackReason": audit.get("classification") if audit.get("fallbackRequired") or audit.get("fallbackUsed") else None})
        metrics.append(traffic_sla_metrics(snapshot, audit, risk))

    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    gate = "FAIL" if any(row["classification"] in {"traffic-matrix-invalid", "traffic-matrix-stale", "traffic-confidence-low", "active-route-traffic-risk"} for row in rows) else "PASS"
    if args.allow_traffic_fallback and gate == "FAIL" and not any(row["classification"] == "traffic-matrix-invalid" for row in rows):
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase82-traffic-matrix-audit/v1", "gate": gate, "productionMainReady": False, "classificationCounts": counts, "snapshotCount": len(rows)}
    write_json(output_dir / "phase82_traffic_summary.json", summary)
    write_json(output_dir / "per_snapshot_traffic_audit.json", rows)
    write_json(output_dir / "traffic_fallback_decisions.json", fallback)
    write_json(output_dir / "traffic_sla_metrics.json", {"schemaVersion": "phase82-traffic-sla-metrics/v1", "rows": metrics})
    (output_dir / "phase82_traffic_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 82 Traffic Matrix Audit",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Production main ready: `{summary.get('productionMainReady')}`",
        f"- Snapshot count: `{summary.get('snapshotCount')}`",
        f"- Classifications: `{json.dumps(summary.get('classificationCounts', {}), sort_keys=True)}`",
        "",
        "Phase 82 audits traffic matrix freshness/confidence/fallback only and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 82 traffic matrix audit.")
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR))
    parser.add_argument("--traffic-max-freshness-seconds", type=int, default=300)
    parser.add_argument("--traffic-min-confidence", type=float, default=0.7)
    parser.add_argument("--require-live-traffic", action="store_true")
    parser.add_argument("--allow-traffic-fallback", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE82 TRAFFIC MATRIX AUDIT] wrote {args.output_dir}")
    return 1 if summary.get("gate") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
