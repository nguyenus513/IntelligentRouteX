from __future__ import annotations

from pathlib import Path

import run_phase81_bottleneck_audit as phase81


def test_quality_classifier_detects_vroom_distance_win() -> None:
    row = {
        "vroomFeasibleByInternalChecker": True,
        "challenger": {"hardViolations": 0, "vehicleCount": 1, "distance": 120},
        "vroom": {"hardViolations": 0, "vehicleCount": 1, "totalDistance": 100},
    }

    assert phase81.quality_gap_classify(row) == "vroom-quality-win-distance"


def test_runtime_classifier_detects_route_pool_bottleneck() -> None:
    row = {"runtimeMs": 31_000, "stageRuntimeSummary": {"stages": [{"name": "route-pool-sp", "runtimeMs": 20_000}, {"name": "incumbent", "runtimeMs": 2_000}]}}

    assert phase81.runtime_bottleneck_classify(row, 30_000) == "route-pool-bottleneck"


def test_active_route_lock_violation_triggers_fallback() -> None:
    audit = phase81.audit_active_route_locking()
    rows = {row["case"]: row for row in audit["rows"]}

    assert rows["locked-prefix-reordered"]["classification"] == "lockedPrefixViolation"
    assert rows["locked-prefix-reordered"]["fallbackApplied"] is True


def test_fault_injection_missing_duration_matrix_fails_safely() -> None:
    audit = phase81.audit_fault_injection()
    rows = {row["case"]: row for row in audit["rows"]}

    assert rows["missing-durationMatrix"]["classification"] == "validation-fail"
    assert rows["missing-durationMatrix"]["crashed"] is False


def test_food_sla_classifier_detects_tail_latency_risk() -> None:
    row = {"orderToDeliveryP95": 90, "orderToDeliveryP99": 110, "lateOrderRate": 0.0, "driverLoadBalance": 0, "batchingRatio": 2}

    assert phase81.food_sla_classify(row) == "tail-latency-risk"


def test_vroom_compatibility_classifier_detects_missing_required_nodes() -> None:
    row = {"vroomStatus": "ok", "supportedMapping": True, "importValid": True, "champion": {"hardViolations": 1, "violations": ["missing-required-nodes"]}}

    assert phase81.vroom_compatibility_classify(row) == "missing-required-nodes"


def test_summary_report_does_not_claim_production_main_ready() -> None:
    report = Path("docs/benchmark/phase81_bottleneck_audit_report.md").read_text(encoding="utf-8")
    weaknesses = Path("docs/benchmark/current_system_weaknesses.md").read_text(encoding="utf-8")
    combined = report + "\n" + weaknesses

    assert "does not claim `PRODUCTION_MAIN_READY`" in combined or "not `PRODUCTION_MAIN_READY`" in combined
    assert "is `PRODUCTION_MAIN_READY`" not in combined
