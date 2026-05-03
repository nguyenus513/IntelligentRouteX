from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase23_reference_gate import build_report
from scripts.import_phase23_reference_solution import customer_diagnostics, normalize_routes


def toy_instance() -> dict:
    return {
        "depotNodeId": "0",
        "nodes": [
            {"id": "0"},
            {"id": "1"},
            {"id": "2"},
            {"id": "3"},
        ],
    }


def test_normalize_routes_adds_depot() -> None:
    normalized = normalize_routes({"routes": [["1", "2"], ["0", "3"]]}, "0")

    assert normalized["routes"] == [["0", "1", "2", "0"], ["0", "3", "0"]]


def test_customer_diagnostics_detects_missing_duplicate_unknown() -> None:
    solution = {"routes": [["0", "1", "1", "9", "0"]]}

    diagnostics = customer_diagnostics(toy_instance(), solution)

    assert diagnostics["missingCustomerCount"] == 2
    assert diagnostics["duplicateCustomerCount"] == 1
    assert diagnostics["unknownCustomerCount"] == 1


def write_candidate(root: Path, *, reference_available: bool = False, reference_feasible: bool = False, seed_gap: int = 2, gap: int = 2, import_count: int = 0) -> None:
    row = {
        "suite": "solomon",
        "instance": "RC101",
        "status": "PASS",
        "feasible": True,
        "seedVehicleGap": seed_gap,
        "vehicleGap": gap,
        "hardViolationCount": 0,
        "referenceRouteAvailable": reference_available,
        "referenceRouteFeasible": reference_feasible,
        "referenceVehicleCount": 14 if reference_available else None,
        "referenceDistance": 1696.94 if reference_available else None,
        "referenceImportCount": import_count,
        "routePoolSizeBefore": 10,
        "routePoolSizeAfter": 10 + import_count,
        "setPartitioningProducedSolution": True,
        "bestLabel": "phase23-reference-route" if reference_feasible else "phase23-seed-incumbent",
        "runtimeMs": 1000,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "phase23_reference_import_results.json").write_text(json.dumps({"results": [row]}), encoding="utf-8")


def test_gate_passes_with_limits_when_reference_missing(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    report = build_report(candidate)

    assert report["verdict"] == "PASS_WITH_LIMITS"
    assert "phase23-reference-route-missing" in report["warnings"]


def test_gate_passes_when_reference_improves_gap(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, reference_available=True, reference_feasible=True, seed_gap=2, gap=0, import_count=14)

    report = build_report(candidate)

    assert report["verdict"] == "PASS"
    assert report["totalGapDelta"] == 2


def test_gate_fails_when_feasible_reference_not_imported(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate, reference_available=True, reference_feasible=True, seed_gap=2, gap=2, import_count=0)

    report = build_report(candidate)

    assert report["verdict"] == "FAIL"
    assert "phase23-reference-not-imported" in report["blockers"]
