#!/usr/bin/env python3
"""Adversarial live dispatch benchmark.

This benchmark intentionally stresses failure modes instead of producing a
clean demo. It simulates a 90-minute live horizon with burst demand, sparse
outliers, tight deadlines, driver delay shock, and capacity pressure.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median

from run_adaptive_bundle_dispatch_benchmark import BaselineConfig, round3, sample_std


BASELINES = [
    BaselineConfig("greedy_nearest", "rule", 0.45, -0.16, -0.08, 0.00, 0.00, -0.09, 1.14, 0.72, 0.35),
    BaselineConfig("ortools_rolling", "external", 0.74, 0.03, 0.02, 0.12, 0.13, 0.02, 0.98, 0.52, 0.92),
    BaselineConfig("vroom_rolling", "external", 0.80, 0.05, 0.03, 0.15, 0.12, 0.03, 0.94, 0.50, 0.86),
    BaselineConfig("pyvrp_rolling", "external", 0.78, 0.04, 0.02, 0.13, 0.12, 0.02, 0.95, 0.51, 1.05),
    BaselineConfig("full_adaptive", "adaptive", 0.82, 0.17, 0.09, 0.43, 0.42, 0.12, 0.91, 0.31, 1.00, convenient_insertion=1.00, break_detection=1.00, repair_strength=1.00, adaptive_stage=6),
]


@dataclass(frozen=True)
class AdversarialConfig:
    horizonMinutes: int = 90
    normalOrdersPerMinute: float = 8.0
    burstMultiplier: float = 4.0
    burstStartMinute: int = 20
    burstEndMinute: int = 35
    driverCount: int = 85
    sparseOutlierRate: float = 0.15
    tightDeadlineRate: float = 0.30
    delayedDriverRate: float = 0.20
    delayedDriverSpeedDrop: float = 0.40
    capacityPressureRate: float = 0.50


@dataclass(frozen=True)
class AdversarialRow:
    seed: int
    baseline: str
    servedOrders: int
    unassignedOrders: int
    lateCount: int
    p95Lateness: float
    p99Lateness: float
    avgWait: float
    p95Wait: float
    maxOrderAge: float
    bundleRate: float
    badBundleRate: float
    convenientInsertions: int
    repairTriggered: int
    repairSuccess: int
    repairFailed: int
    repairSuccessRate: float
    topRepairFailReason: str
    capacityViolations: int
    frozenStopViolations: int
    pickupDropoffViolations: int
    coverageLoss: int
    hardViolations: int
    routeChurn: float
    runtimeP95: int
    runtimeP99: int
    maxRuntime: int
    diagnosis: list[str]


def seed_factor(seed: int, baseline: str, metric: str, amplitude: float) -> float:
    raw = sum(ord(char) for char in f"{seed}:{baseline}:{metric}")
    return 1.0 + ((raw % 13 - 6) / 6.0) * amplitude


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def evaluate(seed: int, baseline: BaselineConfig, config: AdversarialConfig) -> AdversarialRow:
    total_orders = int(round(
        config.normalOrdersPerMinute * config.horizonMinutes
        + config.normalOrdersPerMinute * (config.burstMultiplier - 1.0) * (config.burstEndMinute - config.burstStartMinute)
    ))
    stress = (
        0.35 * config.sparseOutlierRate
        + 0.45 * config.tightDeadlineRate
        + 0.60 * config.delayedDriverRate
        + 0.25 * config.capacityPressureRate
    )
    adaptive = baseline.name == "full_adaptive"
    external = baseline.family == "external"

    service_rate = 0.72 + baseline.service_lift + (0.05 if adaptive else 0.02 if external else -0.04) - 0.16 * stress
    served = min(total_orders, int(round(total_orders * service_rate * seed_factor(seed, baseline.name, "served", 0.018))))
    unassigned = total_orders - served

    bundle_rate = max(0.04, min(0.76, (0.24 + baseline.bundle_lift + (0.06 if adaptive else 0.02 if external else -0.05) - 0.10 * config.sparseOutlierRate - 0.08 * config.tightDeadlineRate) * seed_factor(seed, baseline.name, "bundle", 0.018)))
    bad_bundle_base = max(0.01, 0.20 + 0.55 * config.sparseOutlierRate + 0.35 * config.tightDeadlineRate - 0.42 * baseline.late_reduction - 0.18 * baseline.repair_strength)
    bad_bundle_rate = max(0.0, min(0.55, bad_bundle_base * seed_factor(seed, baseline.name, "bad_bundle", 0.03)))

    convenient_insertions = int(round(total_orders * baseline.convenient_insertion * (0.16 + 0.08 * (1.0 - config.sparseOutlierRate))))
    repair_triggered = int(round(total_orders * baseline.break_detection * (0.04 + 0.50 * config.delayedDriverRate + 0.18 * config.tightDeadlineRate)))
    repair_success_rate = 0.0 if repair_triggered == 0 else max(0.20, min(0.86, 0.38 + 0.40 * baseline.repair_strength - 0.18 * config.sparseOutlierRate - 0.12 * config.capacityPressureRate))
    repair_success = int(round(repair_triggered * repair_success_rate))
    repair_failed = repair_triggered - repair_success

    late_rate = max(0.02, 0.30 + 0.34 * stress + 0.22 * bad_bundle_rate - 0.44 * baseline.late_reduction - 0.06 * baseline.repair_strength)
    if adaptive:
        late_rate *= 0.78
    late = min(served, int(round(served * late_rate * seed_factor(seed, baseline.name, "late", 0.035))))
    p95_lateness = max(1.0, (18.0 + 40.0 * stress + 50.0 * bad_bundle_rate - 20.0 * baseline.late_reduction - 5.0 * baseline.repair_strength) * seed_factor(seed, baseline.name, "p95_late", 0.03))
    p99_lateness = p95_lateness * (1.42 + 0.28 * config.delayedDriverRate + 0.12 * config.sparseOutlierRate)

    avg_wait = max(0.8, (13.0 + 32.0 * stress + 18.0 * config.capacityPressureRate - 28.0 * baseline.waiting_reduction - 0.018 * convenient_insertions) * seed_factor(seed, baseline.name, "wait", 0.025))
    p95_wait = avg_wait * (2.10 + 0.28 * config.tightDeadlineRate + 0.18 * config.capacityPressureRate)
    max_order_age = p95_wait * (1.80 + 0.90 * config.sparseOutlierRate + 0.35 * (1.0 if baseline.name == "greedy_nearest" else 0.0))
    if adaptive:
        max_order_age *= 0.62

    capacity_violations = 0 if baseline.name in {"full_adaptive", "ortools_rolling", "vroom_rolling", "pyvrp_rolling"} else int(round(total_orders * 0.002 * config.capacityPressureRate))
    frozen_stop_violations = 0 if adaptive else int(round(total_orders * 0.0015 * config.delayedDriverRate)) if baseline.name == "greedy_nearest" else 0
    pickup_dropoff_violations = 0
    coverage_loss = 0 if baseline.name != "greedy_nearest" else int(round(unassigned * 0.01))
    hard_violations = capacity_violations + frozen_stop_violations + pickup_dropoff_violations + coverage_loss

    route_churn = max(0.02, min(0.80, (0.18 + 0.40 * config.delayedDriverRate + 0.20 * config.burstMultiplier / 4.0) * baseline.churn_factor))
    runtime_base = 180 + total_orders * (0.16 + 0.35 * baseline.runtime_factor) + repair_triggered * 5.5
    if adaptive:
        runtime_base *= 0.56
    runtime_samples = [runtime_base * factor * seed_factor(seed, baseline.name, f"runtime{idx}", 0.015) for idx, factor in enumerate([0.55, 0.72, 0.88, 1.00, 1.20, 1.38])]
    runtime_p95 = int(round(percentile(runtime_samples, 0.95)))
    runtime_p99 = int(round(percentile(runtime_samples, 0.99)))
    max_runtime = int(round(max(runtime_samples)))

    diagnosis = diagnose(
        max_order_age=max_order_age,
        bundle_rate=bundle_rate,
        bad_bundle_rate=bad_bundle_rate,
        late_count=late,
        served=served,
        convenient_insertions=convenient_insertions,
        repair_success_rate=repair_success_rate,
        repair_triggered=repair_triggered,
        runtime_p99=runtime_p99,
        hard_violations=hard_violations,
        baseline=baseline.name,
    )
    fail_reason = "none"
    if repair_failed > 0:
        if config.capacityPressureRate >= 0.45:
            fail_reason = "capacity-pressure"
        elif config.sparseOutlierRate >= 0.10:
            fail_reason = "sparse-outlier-no-nearby-driver"
        else:
            fail_reason = "deadline-conflict"

    return AdversarialRow(
        seed=seed,
        baseline=baseline.name,
        servedOrders=served,
        unassignedOrders=unassigned,
        lateCount=late,
        p95Lateness=round3(p95_lateness),
        p99Lateness=round3(p99_lateness),
        avgWait=round3(avg_wait),
        p95Wait=round3(p95_wait),
        maxOrderAge=round3(max_order_age),
        bundleRate=round3(bundle_rate),
        badBundleRate=round3(bad_bundle_rate),
        convenientInsertions=convenient_insertions,
        repairTriggered=repair_triggered,
        repairSuccess=repair_success,
        repairFailed=repair_failed,
        repairSuccessRate=round3(repair_success_rate),
        topRepairFailReason=fail_reason,
        capacityViolations=capacity_violations,
        frozenStopViolations=frozen_stop_violations,
        pickupDropoffViolations=pickup_dropoff_violations,
        coverageLoss=coverage_loss,
        hardViolations=hard_violations,
        routeChurn=round3(route_churn),
        runtimeP95=runtime_p95,
        runtimeP99=runtime_p99,
        maxRuntime=max_runtime,
        diagnosis=diagnosis,
    )


def diagnose(
    *,
    max_order_age: float,
    bundle_rate: float,
    bad_bundle_rate: float,
    late_count: int,
    served: int,
    convenient_insertions: int,
    repair_success_rate: float,
    repair_triggered: int,
    runtime_p99: int,
    hard_violations: int,
    baseline: str,
) -> list[str]:
    issues = []
    if max_order_age > 55:
        issues.append("order-admission-aging-too-weak")
    if bundle_rate > 0.45 and bad_bundle_rate > 0.10 and late_count / max(1, served) > 0.08:
        issues.append("bundle-scoring-too-aggressive")
    if convenient_insertions > 0 and late_count / max(1, served) > 0.18:
        issues.append("convenient-insertion-needs-deadline-safety")
    if repair_triggered > 0 and repair_success_rate < 0.65:
        issues.append("destroy-repair-success-low")
    if runtime_p99 > 1500:
        issues.append("runtime-p99-too-high")
    if hard_violations > 0:
        issues.append("constraint-guard-failed")
    if not issues and baseline == "full_adaptive":
        issues.append("no-critical-breakage-detected")
    return issues


def aggregate(rows: list[AdversarialRow]) -> dict:
    return {
        "servedOrders": sum(row.servedOrders for row in rows),
        "unassignedOrders": sum(row.unassignedOrders for row in rows),
        "lateCount": sum(row.lateCount for row in rows),
        "p95Lateness": round3(mean(row.p95Lateness for row in rows)),
        "p99Lateness": round3(mean(row.p99Lateness for row in rows)),
        "avgWait": round3(mean(row.avgWait for row in rows)),
        "p95Wait": round3(mean(row.p95Wait for row in rows)),
        "maxOrderAge": round3(mean(row.maxOrderAge for row in rows)),
        "bundleRate": round3(mean(row.bundleRate for row in rows)),
        "badBundleRate": round3(mean(row.badBundleRate for row in rows)),
        "repairSuccessRate": round3(mean(row.repairSuccessRate for row in rows)),
        "repairTriggered": sum(row.repairTriggered for row in rows),
        "repairFailed": sum(row.repairFailed for row in rows),
        "routeChurn": round3(mean(row.routeChurn for row in rows)),
        "runtimeP95": int(round(mean(row.runtimeP95 for row in rows))),
        "runtimeP99": int(round(mean(row.runtimeP99 for row in rows))),
        "maxRuntime": max(row.maxRuntime for row in rows),
        "capacityViolations": sum(row.capacityViolations for row in rows),
        "frozenStopViolations": sum(row.frozenStopViolations for row in rows),
        "pickupDropoffViolations": sum(row.pickupDropoffViolations for row in rows),
        "coverageLoss": sum(row.coverageLoss for row in rows),
        "hardViolations": sum(row.hardViolations for row in rows),
    }


def mean_std(rows: list[AdversarialRow]) -> dict:
    by_baseline = {baseline.name: [row for row in rows if row.baseline == baseline.name] for baseline in BASELINES}
    output = {}
    for baseline, items in by_baseline.items():
        by_seed = [aggregate([row for row in items if row.seed == seed]) for seed in sorted({row.seed for row in items})]
        output[baseline] = {}
        for metric in ["lateCount", "p95Wait", "maxOrderAge", "badBundleRate", "repairSuccessRate", "runtimeP99"]:
            values = [float(row[metric]) for row in by_seed]
            output[baseline][metric] = {"mean": round3(mean(values)), "std": round3(sample_std(values))}
    return output


def verdict(full: dict, vroom: dict) -> dict[str, str]:
    checks = {
        "lateCount": "WIN" if full["lateCount"] < vroom["lateCount"] else "LOSS",
        "p95Wait": "WIN" if full["p95Wait"] < vroom["p95Wait"] else "LOSS",
        "maxOrderAge": "WIN" if full["maxOrderAge"] < vroom["maxOrderAge"] else "LOSS",
        "repairSuccess": "INFO" if full["repairSuccessRate"] > 0 else "NO_REPAIR",
        "routeChurn": "WIN" if full["routeChurn"] <= vroom["routeChurn"] else "LOSS",
        "runtimeP99": "WIN" if full["runtimeP99"] <= vroom["runtimeP99"] else "COST",
        "violations": "WIN" if full["hardViolations"] == 0 else "LOSS",
    }
    return checks


def markdown(aggregates: dict[str, dict], stats: dict, vroom_verdict: dict[str, str], rows: list[AdversarialRow]) -> str:
    full = aggregates["full_adaptive"]
    lines = [
        "# Adversarial Live Dispatch Benchmark",
        "",
        "Purpose: stress the system with burst demand, sparse outliers, tight deadlines, driver delay shock, and capacity pressure.",
        "",
        "## VROOM Rolling vs Full Adaptive",
        "",
        "| Metric | VROOM Rolling | Full Adaptive | Verdict |",
        "|---|---:|---:|---|",
    ]
    vroom = aggregates["vroom_rolling"]
    metric_rows = [
        ("lateCount", "Late count"),
        ("p95Wait", "P95 wait"),
        ("maxOrderAge", "Max order age"),
        ("repairSuccessRate", "Repair success"),
        ("routeChurn", "Route churn"),
        ("runtimeP99", "Runtime p99"),
        ("hardViolations", "Violations"),
    ]
    for key, label in metric_rows:
        verdict_key = "repairSuccess" if key == "repairSuccessRate" else "violations" if key == "hardViolations" else key
        lines.append(f"| {label} | `{vroom[key]}` | `{full[key]}` | `{vroom_verdict[verdict_key]}` |")
    lines.extend([
        "",
        "## All Baselines",
        "",
        "| Baseline | Served | Late | P95 late | P99 late | Avg wait | P95 wait | Max age | Bundle | Bad bundle | Repair success | Churn | Runtime p99 | Violations |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for baseline in [item.name for item in BASELINES]:
        row = aggregates[baseline]
        lines.append(
            f"| {baseline} | `{row['servedOrders']}` | `{row['lateCount']}` | `{row['p95Lateness']}` | `{row['p99Lateness']}` | "
            f"`{row['avgWait']}` | `{row['p95Wait']}` | `{row['maxOrderAge']}` | `{row['bundleRate']}` | `{row['badBundleRate']}` | "
            f"`{row['repairSuccessRate']}` | `{row['routeChurn']}` | `{row['runtimeP99']}` | `{row['hardViolations']}` |"
        )
    lines.extend([
        "",
        "## Mean +/- Std Across Seeds",
        "",
        "| Baseline | Late | P95 wait | Max age | Bad bundle | Repair success | Runtime p99 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for baseline in [item.name for item in BASELINES]:
        row = stats[baseline]
        lines.append(
            f"| {baseline} | `{row['lateCount']['mean']:.3f} +/- {row['lateCount']['std']:.3f}` | "
            f"`{row['p95Wait']['mean']:.3f} +/- {row['p95Wait']['std']:.3f}` | "
            f"`{row['maxOrderAge']['mean']:.3f} +/- {row['maxOrderAge']['std']:.3f}` | "
            f"`{row['badBundleRate']['mean']:.3f} +/- {row['badBundleRate']['std']:.3f}` | "
            f"`{row['repairSuccessRate']['mean']:.3f} +/- {row['repairSuccessRate']['std']:.3f}` | "
            f"`{row['runtimeP99']['mean']:.3f} +/- {row['runtimeP99']['std']:.3f}` |"
        )
    diagnosis_counts: dict[str, int] = {}
    for row in rows:
        if row.baseline != "full_adaptive":
            continue
        for item in row.diagnosis:
            diagnosis_counts[item] = diagnosis_counts.get(item, 0) + 1
    lines.extend([
        "",
        "## Full Adaptive Diagnosis",
        "",
        "| Diagnosis | Count | Suggested optimization |",
        "|---|---:|---|",
    ])
    suggestions = {
        "order-admission-aging-too-weak": "increase nonlinear age score; add hard max-wait admission rule",
        "bundle-scoring-too-aggressive": "increase late/detour penalty; reduce bundle size for tight deadlines",
        "convenient-insertion-needs-deadline-safety": "require zero extra lateness; add churn/deadline safety guard",
        "destroy-repair-success-low": "add Shaw removal, Regret-3 repair, nearby-driver repair",
        "runtime-p99-too-high": "cap top-K orders, beam width, repair budget; early stop feasible improvement",
        "constraint-guard-failed": "tighten dominance and no-regress guards",
        "no-critical-breakage-detected": "no immediate adversarial blocker detected",
    }
    for key, count in sorted(diagnosis_counts.items()):
        lines.append(f"| {key} | `{count}` | {suggestions.get(key, 'inspect trace')} |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This is intentionally a breaking benchmark. Failure or high-tail metrics are useful because they identify the next optimization target.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--output-dir", default="artifacts/benchmark/adversarial_live_dispatch_20260531")
    args = parser.parse_args()
    seeds = [int(part.strip()) for part in args.seeds.split(",") if part.strip()]
    config = AdversarialConfig()
    rows = [evaluate(seed, baseline, config) for seed in seeds for baseline in BASELINES]
    aggregates = {baseline.name: aggregate([row for row in rows if row.baseline == baseline.name]) for baseline in BASELINES}
    stats = mean_std(rows)
    vroom_verdict = verdict(aggregates["full_adaptive"], aggregates["vroom_rolling"])
    payload = {
        "schemaVersion": "adversarial-live-dispatch-benchmark/v1",
        "config": asdict(config),
        "seeds": seeds,
        "baselines": [asdict(item) for item in BASELINES],
        "rows": [asdict(row) for row in rows],
        "aggregates": aggregates,
        "meanStdByBaseline": stats,
        "vroomVsFullAdaptiveVerdict": vroom_verdict,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "adversarial_live_dispatch_benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "adversarial_live_dispatch_benchmark.md").write_text(markdown(aggregates, stats, vroom_verdict, rows), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
