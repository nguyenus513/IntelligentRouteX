from __future__ import annotations

from run_phase100_final_quality_guard import evaluate_final_gate


def passing_metrics() -> dict:
    return {
        "acceptedRecombinedCandidates": 1,
        "timeWindowViolationCountAfter": 0,
        "rejectedByCoverage": 0,
        "rejectedBySlotOverflow": 0,
        "hardViolations": 0,
        "antiHardcodeGate": "PASS",
    }


def test_phase100_gate_passes_when_all_final_metrics_satisfy_gate() -> None:
    assert evaluate_final_gate(passing_metrics())["gate"] == "PASS"


def test_phase100_gate_fails_when_no_accepted_recombination() -> None:
    metrics = passing_metrics()
    metrics["acceptedRecombinedCandidates"] = 0

    result = evaluate_final_gate(metrics)

    assert result["gate"] == "FAIL"
    assert "acceptedRecombinedCandidates<1" in result["failures"]


def test_phase100_gate_fails_when_time_window_remains() -> None:
    metrics = passing_metrics()
    metrics["timeWindowViolationCountAfter"] = 1

    result = evaluate_final_gate(metrics)

    assert result["gate"] == "FAIL"
    assert "timeWindowViolationCountAfter>0" in result["failures"]


def test_phase100_gate_fails_when_coverage_regresses() -> None:
    metrics = passing_metrics()
    metrics["rejectedByCoverage"] = 1

    result = evaluate_final_gate(metrics)

    assert result["gate"] == "FAIL"
    assert "rejectedByCoverage>0" in result["failures"]


def test_phase100_gate_fails_when_hard_violations_exist() -> None:
    metrics = passing_metrics()
    metrics["hardViolations"] = 1

    result = evaluate_final_gate(metrics)

    assert result["gate"] == "FAIL"
    assert "hardViolations>0" in result["failures"]


def test_phase100_gate_fails_when_antihardcode_not_pass() -> None:
    metrics = passing_metrics()
    metrics["antiHardcodeGate"] = "FAIL"

    result = evaluate_final_gate(metrics)

    assert result["gate"] == "FAIL"
    assert "antiHardcodeGate!=PASS" in result["failures"]
