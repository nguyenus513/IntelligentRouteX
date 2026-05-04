from __future__ import annotations

from pathlib import Path

import generate_phase76_vroom_capability_cases as phase76gen
import run_phase76_vroom_fair_quality_report as fair
import run_phase76_vroom_semantic_audit as semantic


def test_generator_produces_complete_pickup_dropoff_pairs(tmp_path: Path) -> None:
    manifest = phase76gen.generate(tmp_path)
    case = phase76gen.build_case("single_shipment")
    node_ids = {str(node["id"]) for node in case["nodes"]}

    assert manifest["caseCount"] == 15
    assert all(str(req["pickupNodeId"]) in node_ids and str(req["dropoffNodeId"]) in node_ids for req in case["requests"])


def test_capacity_blocks_bundle_expected_requires_more_routes() -> None:
    case = phase76gen.build_case("capacity_blocks_bundle")

    assert case["capacity"] == 1
    assert case["vehicleCount"] == 2
    assert case["capabilityExpected"]["vroomExpected"] == "requires-more-than-one-route"


def test_waiting_required_has_ready_time_after_immediate_arrival() -> None:
    case = phase76gen.build_case("waiting_required")
    pickup = next(node for node in case["nodes"] if node["id"] == "1")

    assert pickup["readyTime"] > 0


def test_custom_matrix_asymmetric_has_asymmetric_matrix() -> None:
    case = phase76gen.build_case("custom_matrix_asymmetric")
    matrix = case["distanceMatrix"]

    assert any(matrix[i][j] != matrix[j][i] for i in range(len(matrix)) for j in range(len(matrix)))


def test_fair_comparator_ignores_quality_when_vroom_infeasible() -> None:
    row = {"classification": "vroom-hard-fail", "vroomFeasibleByInternalChecker": False, "champion": {"hardViolations": 1}, "challenger": {"hardViolations": 0, "overBudget": False}}

    assert fair.fair_classify(row) == "challenger-better-feasibility"


def test_fair_comparator_compares_quality_when_both_feasible() -> None:
    row = {"classification": "vroom-win", "vroomFeasibleByInternalChecker": True, "champion": {"hardViolations": 0, "vehicleCount": 1, "totalDistance": 10}, "challenger": {"hardViolations": 0, "overBudget": False, "vehicleCount": 1, "totalDistance": 12}}

    assert fair.fair_classify(row) == "both-feasible-vroom-distance-win"


def test_semantic_audit_detects_matrix_duration_mismatch() -> None:
    row = {"classification": "tie", "vroomFeasibleByInternalChecker": False, "supportedMapping": True, "importValid": True, "timeUnitDiagnostics": {"suspiciousScaleMismatch": ["matrix-too-large-vs-time-windows"]}}

    assert semantic.classify_row(row) == "matrix-duration-mismatch"


def test_no_instance_name_hardcode() -> None:
    combined = Path("scripts/generate_phase76_vroom_capability_cases.py").read_text(encoding="utf-8") + Path("scripts/run_phase76_vroom_fair_quality_report.py").read_text(encoding="utf-8")
    assert "startswith(\"LRC\")" not in combined
    assert "startswith('LRC')" not in combined
    assert "instanceName ==" not in combined
