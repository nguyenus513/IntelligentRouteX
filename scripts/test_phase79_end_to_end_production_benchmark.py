from __future__ import annotations

from pathlib import Path

import run_phase79_end_to_end_production_benchmark as phase79


def valid_live_snapshot() -> dict:
    return {
        "schemaVersion": "live-dispatch-snapshot/v1",
        "snapshotId": "unit_snapshot",
        "timestamp": "2026-05-04T12:00:00+07:00",
        "region": "unit-region",
        "nodeIds": ["depot", "restaurant", "customer"],
        "orders": [
            {
                "orderId": "order-1",
                "pickupNodeId": "restaurant",
                "dropoffNodeId": "customer",
                "restaurantId": "restaurant",
                "readyTime": 5,
                "dueTime": 60,
                "serviceTimePickup": 2,
                "serviceTimeDropoff": 1,
                "demand": 1,
            }
        ],
        "drivers": [{"driverId": "driver-1", "startNodeId": "depot", "capacity": 2, "shiftStart": 0, "shiftEnd": 120}],
        "activeRoutes": [],
        "durationMatrix": [[0, 5, 12], [5, 0, 8], [12, 8, 0]],
        "trafficContext": {"multiplier": 1.0},
        "restaurantDelay": {"restaurant": 3},
        "cancellationRisk": {"order-1": 0.2},
    }


def test_valid_live_snapshot_converts_to_internal_pdptw() -> None:
    instance = phase79.convert_live_snapshot_to_pdptw_instance(valid_live_snapshot())

    assert instance["schemaVersion"] == "external-benchmark-normalized/v1"
    assert instance["problemType"] == "PDPTW"
    assert instance["instanceName"] == "unit_snapshot"
    assert instance["requests"] == [{"orderId": "order-1", "pickupNodeId": "restaurant", "dropoffNodeId": "customer", "demand": 1, "cancellationRisk": 0.2}]
    assert instance["metadata"]["activeRouteLockingImplemented"] is False


def test_invalid_snapshot_fails_before_solver() -> None:
    snapshot = valid_live_snapshot()
    snapshot.pop("durationMatrix")

    result = phase79.validate_snapshot(snapshot)

    assert result["valid"] is False
    assert any("durationMatrix" in error for error in result["errors"])


def test_fallback_triggers_on_hard_violation() -> None:
    decision = phase79.apply_fallback_policy({"instance": "x", "hardViolations": 1, "overBudget": False, "runtimeMs": 10, "finalSolutionSignature": "sig"}, 30_000)

    assert decision["fallbackApplied"] is True
    assert decision["fallbackReason"] == "challenger-hard-violation"


def test_fair_comparator_does_not_compare_distance_when_vroom_infeasible() -> None:
    challenger = {"hardViolations": 0, "distance": 10}
    vroom = {"supportedMapping": True, "importValid": True, "vroomFeasibleByInternalChecker": False, "champion": {"hardViolations": 1, "totalDistance": 5}, "timeUnitDiagnostics": {}}

    assert phase79.fair_compare(challenger, vroom) == "challenger-better-feasibility"


def test_both_feasible_distance_win_classified_correctly() -> None:
    challenger = {"hardViolations": 0, "distance": 9}
    vroom = {"supportedMapping": True, "importValid": True, "vroomFeasibleByInternalChecker": True, "champion": {"hardViolations": 0, "totalDistance": 12}}

    assert phase79.fair_compare(challenger, vroom) == "both-feasible-challenger-distance-win"


def test_output_report_does_not_claim_production_main_ready() -> None:
    report = Path("docs/benchmark/phase79_end_to_end_benchmark_report.md").read_text(encoding="utf-8")
    gate = Path("docs/production/phase79_benchmark_to_production_gate.md").read_text(encoding="utf-8")
    combined = report + "\n" + gate

    assert "does not claim `PRODUCTION_MAIN_READY`" in combined or "Do not claim `PRODUCTION_MAIN_READY`" in combined
    assert "claim `PRODUCTION_MAIN_READY` from Phase 79 alone" in combined
