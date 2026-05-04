from __future__ import annotations

from pathlib import Path

import run_phase68_system_scorecard as phase68
import run_phase71_food_dispatch_metrics as phase71
import run_phase72_stress_sensitivity_suite as phase72
import run_phase74_final_comprehensive_report as phase74


def test_scorecard_gate_computes_safety_correctly() -> None:
    safety = {"hardViolations": 0}
    runtime = {"overBudgetCount": 0}
    stability = {"repeatOutcomeStable": True, "finalSignatureStable": True}
    comparator = {"gapCounts": {}}

    assert phase68.scorecard_gate(safety, runtime, stability, comparator) == "PASS"
    assert phase68.scorecard_gate({"hardViolations": 1}, runtime, stability, comparator) == "FAIL"


def test_food_metrics_percentiles() -> None:
    values = [1, 2, 3, 4, 5]

    assert phase71.percentile(values, 0.95) == 5
    assert phase71.percentile(values, 0.99) == 5


def test_stress_suite_manifest_generated() -> None:
    manifest = phase72.generate_manifest()

    assert manifest["variantCount"] > 0
    assert {"orders", "driverMode", "trafficMultiplier", "timeWindowTightness", "clusterRatio"}.issubset(manifest["variants"][0].keys())


def test_final_report_includes_phase67c_audit_backed_conclusion() -> None:
    text = phase74.build_report()

    assert "Phase 67B confirms" in text or "Phase 67B" in text
    assert "Quality superiority remains inconclusive" in text


def test_production_checklist_does_not_claim_main_ready_without_live_adapter() -> None:
    text = Path("docs/benchmark/production_readiness_checklist.md").read_text(encoding="utf-8")

    assert "Current status: `CERTIFICATION_SAFE`" in text
    assert "Do **not** mark `PRODUCTION_MAIN_READY`" in text
    assert "live orders/drivers/activeRoutes adapter" in text
