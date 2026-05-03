from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase19_bks_compatibility_gate import build_report
from scripts.reference_solution_loader import load_reference_solution, parse_reference_text
from scripts.solomon_distance_semantics import distance_matrix, instance_with_distance_mode, transform_distance


def test_distance_modes_transform_values() -> None:
    assert transform_distance(1.6, "euclidean_round_nearest") == 2.0
    assert transform_distance(1.6, "euclidean_floor") == 1.0
    assert transform_distance(1.1, "euclidean_ceil") == 2.0
    assert transform_distance(1.678, "euclidean_truncate_1_decimal") == 1.6


def test_distance_matrix_rebuilds_instance_copy() -> None:
    instance = {"nodes": [{"id": "0", "x": 0, "y": 0}, {"id": "1", "x": 3, "y": 4}], "distanceMatrix": [[0, 0], [0, 0]]}

    rebuilt = instance_with_distance_mode(instance, "euclidean_round_nearest")

    assert rebuilt["distanceMatrix"][0][1] == 5.0
    assert instance["distanceMatrix"][0][1] == 0
    assert distance_matrix(instance["nodes"], "euclidean_float")[0][1] == 5.0


def test_reference_loader_supports_text_and_json(tmp_path: Path) -> None:
    text_routes = parse_reference_text("Route 1: 1 2 3\nRoute 2: 4 5")
    assert text_routes == [["0", "1", "2", "3", "0"], ["0", "4", "5", "0"]]

    path = tmp_path / "RC101.json"
    path.write_text(json.dumps({"instance": "RC101", "routes": [["0", "1", "0"]]}), encoding="utf-8")
    solution = load_reference_solution(path)
    assert solution["routes"] == [["0", "1", "0"]]


def write_audit(root: Path, *, reference_available: bool = False, reference_feasible: bool = False, missing_distance: bool = False) -> None:
    payload = {
        "instance": "RC101",
        "instanceFingerprint": {"bestKnown": {"vehicleCount": 14, "objective": 1696.94}},
        "incumbentChecked": {"feasible": True, "vehicleCount": 16, "totalDistance": 1721.0},
        "distanceSemantics": [] if missing_distance else [{"mode": "euclidean_float", "feasible": True}],
        "checkerSemantics": [{"mode": "epsilon=1e-9", "feasibleByTimeWindows": True}],
        "referenceRouteAvailable": reference_available,
        "referenceRouteChecked": {"feasible": reference_feasible, "vehicleCount": 14} if reference_available else None,
        "compatibilityConclusion": "reference-route-feasible-model-compatible" if reference_feasible else "model-compatible-reference-route-missing-solver-gap-likely",
        "recommendedNextStep": "obtain-or-generate-reference-14-vehicle-route-file-for-rc101",
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase19_bks_compatibility_audit.json").write_text(json.dumps(payload), encoding="utf-8")


def test_gate_passes_with_limits_without_reference(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_audit(candidate)

    report = build_report(candidate)

    assert report["verdict"] == "PASS_WITH_LIMITS"


def test_gate_passes_strict_with_feasible_reference(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_audit(candidate, reference_available=True, reference_feasible=True)

    report = build_report(candidate)

    assert report["verdict"] == "PASS"


def test_gate_fails_when_distance_semantics_missing(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_audit(candidate, missing_distance=True)

    report = build_report(candidate)

    assert report["verdict"] == "FAIL"
    assert "phase19-missing-distance-semantics" in report["blockers"]
