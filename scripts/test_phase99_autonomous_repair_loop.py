from __future__ import annotations

from run_phase99_autonomous_repair_loop import classify_blocker, patch_prompt, success


def base_summary() -> dict:
    return {
        "acceptedRecombinedCandidates": 0,
        "timeWindowViolationCountAfter": 2,
        "hardViolations": 0,
        "rejectedByCoverage": 0,
        "rejectedBySlotOverflow": 0,
        "rejectedByTimeWindow": 1,
        "antiHardcodeGate": "PASS",
    }


def test_autonomous_loop_classifies_success() -> None:
    summary = base_summary()
    summary.update({"acceptedRecombinedCandidates": 1, "timeWindowViolationCountAfter": 0, "rejectedByTimeWindow": 0})

    assert success(summary)
    assert classify_blocker(summary) == "success"


def test_autonomous_loop_classifies_time_window_residual() -> None:
    assert classify_blocker(base_summary()) == "time-window-residual"


def test_autonomous_loop_classifies_coverage_regression() -> None:
    summary = base_summary()
    summary["rejectedByCoverage"] = 1

    assert classify_blocker(summary) == "coverage-regression"


def test_autonomous_loop_classifies_slot_overflow_regression() -> None:
    summary = base_summary()
    summary["rejectedBySlotOverflow"] = 1

    assert classify_blocker(summary) == "slot-overflow-regression"


def test_autonomous_loop_patch_prompt_contains_safety_rules() -> None:
    prompt = patch_prompt(1, "time-window-residual", base_summary())

    assert "no target-K forcing" in prompt
    assert "no instance-name" in prompt
    assert "phase99_exact_tw_route_finalizer.py" in prompt
