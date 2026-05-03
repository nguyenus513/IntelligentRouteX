from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase13_hgs_route_pool_gate import build_report, main


def write_baseline(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {'suite': 'solomon', 'instance': 'RC101', 'vehicleGap': 2},
        {'suite': 'li-lim', 'instance': 'LR101', 'vehicleGap': None},
        {'suite': 'li-lim', 'instance': 'LRC101', 'vehicleGap': None},
    ]
    (root / 'phase12_route_pool_results.json').write_text(json.dumps({'results': rows}), encoding='utf-8')


def write_candidate(root: Path, *, imported: int = 3, gap: int = 2, runtime: int = 1000) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {'suite': 'solomon', 'instance': 'RC101', 'status': 'PASS', 'vehicleGap': gap, 'routePoolSize': 20, 'hgsAvailable': True, 'hgsStatus': 'PASS', 'hgsVehicleCount': 16, 'hgsRoutesImported': imported, 'setPartitioningProducedSolution': True, 'runtimeMs': runtime},
        {'suite': 'li-lim', 'instance': 'LR101', 'status': 'SKIPPED', 'vehicleGap': None, 'routePoolSize': 0, 'hgsAvailable': False, 'hgsEvidenceGapReason': 'deferred', 'setPartitioningProducedSolution': False, 'runtimeMs': 0},
        {'suite': 'li-lim', 'instance': 'LRC101', 'status': 'SKIPPED', 'vehicleGap': None, 'routePoolSize': 0, 'hgsAvailable': False, 'hgsEvidenceGapReason': 'deferred', 'setPartitioningProducedSolution': False, 'runtimeMs': 0},
    ]
    (root / 'phase12_route_pool_results.json').write_text(json.dumps({'results': rows}), encoding='utf-8')


def test_gate_passes_with_limits_when_hgs_imports_without_gap_reduction(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_baseline(baseline)
    write_candidate(candidate)

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'PASS_WITH_LIMITS'
    assert report['hgsEvidence'] is True


def test_gate_passes_strict_when_gap_reduces(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_baseline(baseline)
    write_candidate(candidate, gap=1)

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'PASS'
    assert report['totalGapDelta'] == 1


def test_gate_fails_when_hgs_available_but_not_imported(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_baseline(baseline)
    write_candidate(candidate, imported=0)

    report = build_report(baseline, candidate, 15_000)

    assert report['verdict'] == 'FAIL'
    assert 'phase13-hgs-routes-not-imported' in report['blockers']


def test_cli_writes_outputs(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    output = tmp_path / 'out'
    write_baseline(baseline)
    write_candidate(candidate)

    assert main(['--baseline-dir', str(baseline), '--candidate-dir', str(candidate), '--output-dir', str(output)]) == 0
    assert (output / 'phase13_hgs_route_pool_gate.json').exists()
    assert (output / 'phase13_hgs_route_pool_gate.md').exists()
