from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import scripts.generate_benchmark_tables as tables


def phase15_row(solver: str, feasible: bool, distance: float, vehicles: int, instance: str = "LC101") -> dict:
    return {
        "solver": solver,
        "suite": "li-lim",
        "instance": instance,
        "feasible": feasible,
        "vehicleCount": vehicles,
        "totalDistance": distance,
        "runtimeMs": 1000,
        "phase15TimeLimitMs": 60_000,
        "servedRequestCount": 100,
        "bestKnownDistance": 100.0,
        "bestKnownVehicleCount": 1,
        "capacityViolationCount": 0,
        "timeWindowViolationCount": 0,
        "pickupBeforeDropoffViolationCount": 0,
        "vehicleLimitViolationCount": 0,
    }


def test_gap_formula_uses_baseline_distance() -> None:
    assert tables.gap_pct(110.0, 100.0) == 10.0
    assert tables.gap_pct(90.0, 100.0) == -10.0
    assert tables.gap_pct(90.0, 0.0) is None


def test_infeasible_rows_excluded_from_distance_gap_average() -> None:
    rows = tables.paired_solver_rows([
        phase15_row("our-dispatch-v2", True, 110.0, 2, "A"),
        phase15_row("ortools-baseline", True, 100.0, 1, "A"),
        phase15_row("our-dispatch-v2", False, 1000.0, 9, "B"),
        phase15_row("ortools-baseline", True, 100.0, 1, "B"),
    ])

    summary = tables.aggregate_phase15(rows)

    assert summary[0]["instances"] == 2
    assert summary[0]["paired_feasible_instances"] == 1
    assert summary[0]["avg_distance_gap_vs_ortools_pct"] == 10.0


def test_build_handles_missing_artifacts_without_crashing(tmp_path: Path) -> None:
    args = Namespace(
        overnight=tmp_path / "missing-overnight",
        vroom_smoke=tmp_path / "missing-smoke",
        vroom_lilim=tmp_path / "missing-lilim",
        commit="test",
    )

    data = tables.build(args)

    assert data["inputStatus"] == "missing_input_artifact"
    assert data["phase15_pairs"] == []
    assert data["vroom_lilim_rows"] == []
    assert data["ml_rows"] == []


def test_rendered_markdown_has_no_internal_verdict_or_raw_missing_placeholder(tmp_path: Path) -> None:
    data = {
        "phase15_summary": [{
            "dataset": "li-lim",
            "scale": "small",
            "instances": 1,
            "paired_feasible_instances": 1,
            "ours_feasible_rate_pct": 100.0,
            "avg_vehicle_gap_vs_ortools": 0,
            "avg_distance_gap_vs_ortools_pct": 1.0,
            "avg_runtime_sec": 1.0,
            "hard_violation_rows": 0,
        }],
        "vroom_lilim_rows": [],
        "ml_rows": [],
        "food": {},
        "dynamic": {},
    }

    text = tables.render_tables(data)

    assert "PASS" not in text
    assert "PASS_WITH_LIMITS" not in text
    assert "n/a" not in text.lower()


def test_manifest_records_hashes(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    artifact = output / "sample.csv"
    artifact.write_text("a,b\n1,2\n", encoding="utf-8")
    args = Namespace(
        source_commit="source",
        report_commit="report",
        commit="generation",
        overnight=Path("overnight"),
        vroom_smoke=Path("smoke"),
        vroom_lilim=Path("lilim"),
    )

    tables.write_manifest(output, args, [artifact], {"inputStatus": "complete", "missingInputs": []})

    text = (output / "MANIFEST.md").read_text(encoding="utf-8")
    assert "source_commit: `source`" in text
    assert "report_commit: `report`" in text
    assert "sha256" in text
