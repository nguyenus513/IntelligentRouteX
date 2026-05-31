#!/usr/bin/env python3
"""Deterministic demo metrics for Adaptive ML-Bundle Dispatch.

This is a lightweight report/demo runner, not a production optimizer entrypoint.
It mirrors the implemented layer formulas to expose three explainable scenarios:
1) nearby/same-direction bundle,
2) convenient insertion on an active route,
3) break-risk-triggered destroy-repair.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class ScenarioMetric:
    scenario: str
    bundleScore: float
    assignmentCost: float
    insertExtraCost: float
    breakRisk: float
    repairSuccess: bool
    lateBefore: int
    lateAfter: int
    distanceBefore: float
    distanceAfter: float
    notes: str


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def round3(value: float) -> float:
    return round(value + 1e-12, 3)


def bundle_score(pair_support: float, direction_fit: float, deadline_fit: float,
                 sequence_quality: float, age_balance: float, late_penalty: float) -> float:
    distance_saving = clamp(pair_support / 2.0)
    detour_penalty = clamp(1.0 - pair_support)
    return round3(
        0.20 * pair_support
        + 0.20 * direction_fit
        + 0.20 * deadline_fit
        + 0.15 * distance_saving
        + 0.15 * sequence_quality
        + 0.10 * age_balance
        - 0.30 * detour_penalty
        - 0.40 * late_penalty
    )


def assignment_cost(insert_cost: float, late_penalty: float, detour_penalty: float,
                    churn_penalty: float, driver_fit: float, score: float) -> float:
    return round3(
        0.30 * insert_cost
        + 0.25 * late_penalty
        + 0.20 * detour_penalty
        + 0.15 * churn_penalty
        - 0.10 * driver_fit
        - 0.10 * score
    )


def break_risk(late_risk: float, detour_risk: float, old_order_risk: float,
               overload_risk: float, churn_risk: float) -> float:
    return round3(
        0.35 * late_risk
        + 0.25 * detour_risk
        + 0.15 * old_order_risk
        + 0.15 * overload_risk
        + 0.10 * churn_risk
    )


def build_scenarios() -> list[ScenarioMetric]:
    score_near = bundle_score(0.92, 0.90, 0.88, 0.86, 0.35, 0.12)
    cost_near = assignment_cost(0.18, 0.10, 0.08, 0.05, 0.91, score_near)

    score_insert = bundle_score(0.84, 0.82, 0.80, 0.83, 0.50, 0.18)
    cost_insert = assignment_cost(0.12, 0.14, 0.10, 0.06, 0.88, score_insert)

    risk_bad = break_risk(0.86, 0.78, 0.72, 0.40, 0.62)
    score_repaired = bundle_score(0.70, 0.72, 0.68, 0.75, 0.65, 0.28)
    cost_repaired = assignment_cost(0.24, 0.25, 0.22, 0.18, 0.74, score_repaired)

    return [
        ScenarioMetric(
            scenario="nearby_same_direction_bundle",
            bundleScore=score_near,
            assignmentCost=cost_near,
            insertExtraCost=0.0,
            breakRisk=break_risk(0.12, 0.08, 0.20, 0.0, 0.05),
            repairSuccess=False,
            lateBefore=0,
            lateAfter=0,
            distanceBefore=8.40,
            distanceAfter=7.55,
            notes="Nearby pickup and aligned dropoff create a high-quality bundle.",
        ),
        ScenarioMetric(
            scenario="driver_passing_convenient_insertion",
            bundleScore=score_insert,
            assignmentCost=cost_insert,
            insertExtraCost=0.12,
            breakRisk=break_risk(0.18, 0.10, 0.32, 0.0, 0.06),
            repairSuccess=False,
            lateBefore=0,
            lateAfter=0,
            distanceBefore=9.80,
            distanceAfter=9.05,
            notes="Active route keeps frozen stop and inserts a nearby order behind it.",
        ),
        ScenarioMetric(
            scenario="bad_bundle_break_risk_destroy_repair",
            bundleScore=score_repaired,
            assignmentCost=cost_repaired,
            insertExtraCost=0.24,
            breakRisk=risk_bad,
            repairSuccess=True,
            lateBefore=2,
            lateAfter=1,
            distanceBefore=13.40,
            distanceAfter=12.10,
            notes="High breakRisk triggers ALNS-style destroy-repair before commit.",
        ),
    ]


def markdown(rows: list[ScenarioMetric]) -> str:
    lines = [
        "# Adaptive ML-Bundle Dispatch Demo Metrics",
        "",
        "| Scenario | bundleScore | assignmentCost | insertExtraCost | breakRisk | repairSuccess | lateBefore -> lateAfter | distanceBefore -> distanceAfter |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.scenario} | {row.bundleScore:.3f} | {row.assignmentCost:.3f} | "
            f"{row.insertExtraCost:.3f} | {row.breakRisk:.3f} | {row.repairSuccess} | "
            f"{row.lateBefore} -> {row.lateAfter} | {row.distanceBefore:.2f} -> {row.distanceAfter:.2f} |"
        )
    lines.extend([
        "",
        "## Summary",
        f"- Avg bundleScore: {mean(row.bundleScore for row in rows):.3f}",
        f"- Avg assignmentCost: {mean(row.assignmentCost for row in rows):.3f}",
        f"- Repairs succeeded: {sum(1 for row in rows if row.repairSuccess)}/{len(rows)}",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts/benchmark/adaptive_bundle_dispatch_demo")
    args = parser.parse_args()
    rows = build_scenarios()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "adaptive-bundle-dispatch-demo/v1",
        "scenarios": [asdict(row) for row in rows],
        "summary": {
            "avgBundleScore": round3(mean(row.bundleScore for row in rows)),
            "avgAssignmentCost": round3(mean(row.assignmentCost for row in rows)),
            "repairSuccessCount": sum(1 for row in rows if row.repairSuccess),
        },
    }
    (output_dir / "adaptive_bundle_dispatch_demo.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "adaptive_bundle_dispatch_demo.md").write_text(markdown(rows), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
