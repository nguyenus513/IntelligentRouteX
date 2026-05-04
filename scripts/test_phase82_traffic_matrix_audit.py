from __future__ import annotations

from pathlib import Path

from run_phase82_traffic_matrix_audit import active_route_traffic_risk
from traffic.phase82_matrix_validator import audit_traffic_matrix
from traffic.phase82_synthetic_traffic_provider import SyntheticTrafficProvider


def snapshot() -> dict:
    return {
        "schemaVersion": "live-dispatch-snapshot/v1",
        "snapshotId": "traffic-unit",
        "timestamp": "2026-05-04T12:00:00+07:00",
        "region": "hcm",
        "nodeIds": ["depot", "pickup", "dropoff"],
        "orders": [{"orderId": "o1", "pickupNodeId": "pickup", "dropoffNodeId": "dropoff", "restaurantId": "pickup", "readyTime": 0, "dueTime": 90, "serviceTimePickup": 1, "serviceTimeDropoff": 1, "demand": 1}],
        "drivers": [{"driverId": "d1", "startNodeId": "depot", "capacity": 2, "shiftStart": 0, "shiftEnd": 120}],
        "activeRoutes": [],
        "durationMatrix": [[0, 10, 30], [10, 0, 20], [30, 20, 0]],
        "trafficContext": {"provider": "synthetic", "generatedAt": "2026-05-04T11:59:00+07:00", "validUntil": "2026-05-04T12:04:00+07:00", "trafficMode": "normal", "multiplier": 1.0, "confidence": 0.9, "matrixSource": "live", "freshnessSeconds": 60, "maxFreshnessSeconds": 300},
        "restaurantDelay": {"pickup": 0},
        "cancellationRisk": {"o1": 0.1},
    }


def test_fresh_traffic_matrix_passes() -> None:
    result = audit_traffic_matrix(snapshot(), 300, 0.7)

    assert result["classification"] == "traffic-matrix-healthy"


def test_stale_matrix_fails_or_fallback_depending_flag() -> None:
    stale = snapshot()
    stale["trafficContext"]["freshnessSeconds"] = 900

    assert audit_traffic_matrix(stale, 300, 0.7)["classification"] == "traffic-matrix-stale"
    assert audit_traffic_matrix(stale, 300, 0.7, allow_traffic_fallback=True)["classification"] == "traffic-fallback-used"


def test_low_confidence_triggers_fallback() -> None:
    low = snapshot()
    low["trafficContext"]["confidence"] = 0.2

    assert audit_traffic_matrix(low, 300, 0.7)["classification"] == "traffic-confidence-low"


def test_non_square_and_negative_matrix_fail() -> None:
    bad = snapshot()
    bad["durationMatrix"] = [[0, -1], [1, 0], [2, 3]]

    result = audit_traffic_matrix(bad, 300, 0.7)
    assert result["classification"] == "traffic-matrix-invalid"
    assert result["errors"]


def test_rain_multiplier_increases_durations_deterministically() -> None:
    provider = SyntheticTrafficProvider()
    result = provider.build_duration_matrix([{"id": "a"}, {"id": "b"}], "hcm", "2026-05-04T12:00:00+07:00", {"baseDurationMatrix": [[0, 10], [10, 0]], "trafficMode": "rain", "multiplier": 1.5})

    assert result.durationMatrix == [[0.0, 18.0], [18.0, 0.0]]


def test_active_route_traffic_risk_detected() -> None:
    risky = snapshot()
    risky["activeRoutes"] = [{"driverId": "d1", "route": ["depot", "pickup", "dropoff"], "lockedPrefixLength": 3}]
    risky["trafficContext"]["activeRouteRiskThreshold"] = 20

    assert active_route_traffic_risk(risky)["activeRouteTrafficRiskCount"] == 1


def test_docs_do_not_claim_production_main_ready() -> None:
    combined = Path("docs/production/traffic_matrix_policy.md").read_text(encoding="utf-8") + Path("docs/benchmark/phase82_traffic_aware_benchmark_report.md").read_text(encoding="utf-8")

    assert "does not claim `PRODUCTION_MAIN_READY`" in combined
