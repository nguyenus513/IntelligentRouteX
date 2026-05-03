from __future__ import annotations

import json
from pathlib import Path

from scripts.build_phase12_route_pool_gate import build_report, main


def write_baseline(root: Path) -> None:
    for suite, instance, vehicles, best in [('solomon', 'RC101', 16, 14), ('li-lim', 'LR101', 20, 19), ('li-lim', 'LRC101', 16, 14)]:
        path = root / suite / 'external_benchmark_results.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'results': []}
        payload['results'].append({'suite': suite, 'instance': instance, 'solver': 'our-dispatch-v2', 'vehicleCount': vehicles, 'bestKnownVehicleCount': best})
        path.write_text(json.dumps(payload), encoding='utf-8')


def write_candidate(root: Path, *, pool: int = 10, sp: bool = True, gap: int = 2) -> None:
    rows = [
        {'suite': 'solomon', 'instance': 'RC101', 'status': 'PASS', 'vehicleGap': gap, 'routePoolSize': pool, 'setPartitioningProducedSolution': sp, 'bestLabel': 'phase12-set-partitioning-route-pool', 'runtimeMs': 100},
        {'suite': 'li-lim', 'instance': 'LR101', 'status': 'SKIPPED', 'vehicleGap': None, 'routePoolSize': 0, 'setPartitioningProducedSolution': False, 'reasons': ['deferred']},
        {'suite': 'li-lim', 'instance': 'LRC101', 'status': 'SKIPPED', 'vehicleGap': None, 'routePoolSize': 0, 'setPartitioningProducedSolution': False, 'reasons': ['deferred']},
    ]
    root.mkdir(parents=True, exist_ok=True)
    (root / 'phase12_route_pool_results.json').write_text(json.dumps({'results': rows}), encoding='utf-8')


def test_gate_passes_with_limits_when_seed_evidence_exists(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_baseline(baseline)
    write_candidate(candidate)

    report = build_report(baseline, candidate)

    assert report['verdict'] == 'PASS_WITH_LIMITS'
    assert report['hasSeedEvidence'] is True


def test_gate_blocks_empty_route_pool(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    write_baseline(baseline)
    write_candidate(candidate, pool=0, sp=False)

    report = build_report(baseline, candidate)

    assert report['verdict'] == 'FAIL'
    assert 'phase12-route-pool-empty' in report['blockers']


def test_cli_writes_outputs(tmp_path: Path) -> None:
    baseline = tmp_path / 'baseline'
    candidate = tmp_path / 'candidate'
    output = tmp_path / 'out'
    write_baseline(baseline)
    write_candidate(candidate)

    assert main(['--baseline-dir', str(baseline), '--candidate-dir', str(candidate), '--output-dir', str(output)]) == 0
    assert (output / 'phase12_route_pool_gate.json').exists()
    assert (output / 'phase12_route_pool_gate.md').exists()
