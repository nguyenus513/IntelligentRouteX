from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase10_gap_reduction_gate import build_report, main


def write_result(root: Path, suite: str, instance: str, vehicle_count: int, best: int, *, trace: bool = True) -> None:
    result_path = root / 'our-dispatch-v2' / suite / 'external_benchmark_results.json'
    solution_path = root / 'our-dispatch-v2' / suite / 'solutions' / f'{instance}.json'
    result_path.parent.mkdir(parents=True, exist_ok=True)
    solution_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {"results": []}
    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding='utf-8'))
    solution = {"routes": []}
    if trace:
        solution["globalConsolidation"] = {"operatorAttempts": 2, "acceptedMoves": 0, "topRejectReasons": {"not-better": 2}}
    solution_path.write_text(json.dumps(solution), encoding='utf-8')
    existing["results"].append({
        "suite": suite,
        "instance": instance,
        "solver": "our-dispatch-v2",
        "feasible": True,
        "vehicleCount": vehicle_count,
        "bestKnownVehicleCount": best,
        "totalDistance": 100.0,
        "capacityViolationCount": 0,
        "timeWindowViolationCount": 0,
        "pickupBeforeDropoffViolationCount": 0,
        "vehicleLimitViolationCount": 0,
        "runtimeMs": 100,
        "verdict": "PASS_WITH_LIMITS",
        "solutionPath": str(solution_path),
    })
    result_path.write_text(json.dumps(existing), encoding='utf-8')


def write_all(root: Path, values: dict[tuple[str, str], tuple[int, int]], *, trace: bool = True) -> None:
    for (suite, instance), (vehicles, best) in values.items():
        write_result(root, suite, instance, vehicles, best, trace=trace)


def test_gate_passes_strict_when_gap_decreases(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_all(baseline, {('solomon', 'RC101'): (16, 14), ('li-lim', 'LR101'): (20, 19), ('li-lim', 'LRC101'): (16, 14)})
    write_all(candidate, {('solomon', 'RC101'): (15, 14), ('li-lim', 'LR101'): (20, 19), ('li-lim', 'LRC101'): (16, 14)})

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'PASS'
    assert report['totalGapDelta'] == 1


def test_gate_passes_with_limits_when_trace_exists_but_gap_same(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    values = {('solomon', 'RC101'): (16, 14), ('li-lim', 'LR101'): (20, 19), ('li-lim', 'LRC101'): (16, 14)}
    write_all(baseline, values)
    write_all(candidate, values)

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'PASS_WITH_LIMITS'
    assert report['pass'] is True


def test_gate_fails_without_trace(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    values = {('solomon', 'RC101'): (16, 14), ('li-lim', 'LR101'): (20, 19), ('li-lim', 'LRC101'): (16, 14)}
    write_all(baseline, values)
    write_all(candidate, values, trace=False)

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'FAIL'
    assert 'phase10-no-improvement-trace' in report['blockers']


def test_cli_writes_outputs(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    out = tmp_path / 'out'
    values = {('solomon', 'RC101'): (16, 14), ('li-lim', 'LR101'): (20, 19), ('li-lim', 'LRC101'): (16, 14)}
    write_all(baseline, values)
    write_all(candidate, values)

    assert main(['--baseline-dir', str(baseline), '--candidate-dir', str(candidate), '--output-dir', str(out)]) == 0
    assert (out / 'phase10_gap_reduction_gate.json').exists()
    assert (out / 'phase10_gap_reduction_gate.md').exists()
