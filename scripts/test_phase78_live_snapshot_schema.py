from __future__ import annotations

from pathlib import Path

import validate_phase78_live_snapshot_schema as phase78


def valid_snapshot() -> dict:
    return {
        "schemaVersion": "live-dispatch-snapshot/v1",
        "snapshotId": "snap-001",
        "timestamp": "2026-05-04T07:00:00Z",
        "region": "hcm-core",
        "orders": [
            {
                "orderId": "order-1",
                "pickupNodeId": "restaurant-1",
                "dropoffNodeId": "customer-1",
                "restaurantId": "restaurant-1",
                "readyTime": 600,
                "dueTime": 1800,
                "serviceTimePickup": 120,
                "serviceTimeDropoff": 90,
                "demand": 1,
            }
        ],
        "drivers": [
            {
                "driverId": "driver-1",
                "startNodeId": "driver-start-1",
                "capacity": 2,
                "shiftStart": 0,
                "shiftEnd": 3600,
            }
        ],
        "activeRoutes": [],
        "durationMatrix": [[0, 300, 600], [300, 0, 240], [600, 240, 0]],
        "trafficContext": {"multiplier": 1.0, "generatedAt": "2026-05-04T06:59:00Z", "validUntil": "2026-05-04T07:04:00Z", "confidence": 0.9, "freshnessSeconds": 60, "maxFreshnessSeconds": 300, "matrixSource": "live"},
        "restaurantDelay": {"restaurant-1": 0},
        "cancellationRisk": {"order-1": 0.1},
    }


def test_valid_snapshot_passes() -> None:
    result = phase78.validate_snapshot(valid_snapshot())

    assert result == {"valid": True, "errors": []}


def test_missing_active_routes_fails() -> None:
    snapshot = valid_snapshot()
    snapshot.pop("activeRoutes")

    result = phase78.validate_snapshot(snapshot)

    assert result["valid"] is False
    assert any("activeRoutes" in error for error in result["errors"])


def test_missing_duration_matrix_fails() -> None:
    snapshot = valid_snapshot()
    snapshot.pop("durationMatrix")

    result = phase78.validate_snapshot(snapshot)

    assert result["valid"] is False
    assert any("durationMatrix" in error for error in result["errors"])


def test_invalid_order_time_window_fails() -> None:
    snapshot = valid_snapshot()
    snapshot["orders"][0]["readyTime"] = 2000


    result = phase78.validate_snapshot(snapshot)

    assert result["valid"] is False
    assert any("readyTime must be <= dueTime" in error for error in result["errors"])


def test_invalid_traffic_confidence_fails() -> None:
    snapshot = valid_snapshot()
    snapshot["trafficContext"]["confidence"] = 1.5

    result = phase78.validate_snapshot(snapshot)

    assert result["valid"] is False
    assert any("trafficContext.confidence" in error for error in result["errors"])


def test_fallback_policy_mentions_required_triggers() -> None:
    text = Path("docs/production/fallback_and_rollback_policy.md").read_text(encoding="utf-8").lower()

    assert "timeout" in text
    assert "hard violation" in text
    assert "matrix unavailable" in text or "invalid `durationmatrix`" in text or "missing or invalid `durationmatrix`" in text


def test_docs_do_not_claim_production_main_ready() -> None:
    docs = [
        Path("docs/production/live_snapshot_schema.md"),
        Path("docs/production/solver_api_contract.md"),
        Path("docs/production/fallback_and_rollback_policy.md"),
        Path("docs/production/monitoring_sla_dashboard.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)

    assert "not `PRODUCTION_MAIN_READY`" in combined or "must not be marked `PRODUCTION_MAIN_READY`" in combined
    assert "is `PRODUCTION_MAIN_READY`" not in combined
    assert "marked `PRODUCTION_MAIN_READY`" not in combined.replace("must not be marked `PRODUCTION_MAIN_READY`", "")
