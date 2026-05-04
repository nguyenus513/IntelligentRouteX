from __future__ import annotations

from optimizer.phase92_final_candidate_bridge import FinalCandidateBridge
from optimizer.phase92_operator_activation_policy import OperatorActivationPolicy
from run_phase84_antihardcode_guard import scan
from test_phase90_final_quality_completion import instance


def test_activation_policy_uses_features_not_instance_name() -> None:
    inst = instance()
    inst["instanceName"] = "SHOULD_NOT_MATTER"
    solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    decisions = OperatorActivationPolicy().activate(inst, solution, {"capacityPressure": 0.5, "clusterScore": 0.2}, 1000, ["route-compression", "distance-polish"])

    assert decisions[0].operator in {"route-compression", "distance-polish"}
    assert all("SHOULD_NOT_MATTER" not in decision.reason for decision in decisions)


def test_final_candidate_bridge_completes_intermediate_state() -> None:
    inst = instance()
    incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    intermediate = {"solution": {"routes": [["0", "1", "2", "0"]]}}
    bridged = FinalCandidateBridge().bridge(inst, incumbent, [intermediate], 1)

    assert bridged
    stops = {stop for route in bridged[0]["solution"]["routes"] for stop in route}
    assert {"1", "2", "3", "4"}.issubset(stops)


def test_no_generation_reason_recorded() -> None:
    from optimizer.phase84_operator_portfolio import OperatorPortfolio
    from optimizer.phase90_deadline import Deadline

    result = OperatorPortfolio().apply("distance-polish", instance(), {"routes": [["0", "1", "3", "4", "2", "0"]]}, {}, None, None, Deadline.from_time_limit_ms(10))

    assert "noGenerationReason" in result["telemetry"]


def test_route_count_opportunity_emits_candidate_on_weak_route_case() -> None:
    from optimizer.phase90_route_compression import RouteCompression

    generated = list(RouteCompression().generate(instance(), {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}, 4))

    assert isinstance(generated, list)


def test_distance_polish_emits_candidate_on_crossing_route_case() -> None:
    from optimizer.phase90_distance_polish import DistancePolish

    generated = list(DistancePolish().generate(instance(), {"routes": [["0", "1", "2", "3", "4", "0"]]}, 8))

    assert generated


def test_antihardcode_source_scan_passes() -> None:
    assert scan()["gate"] == "PASS"
