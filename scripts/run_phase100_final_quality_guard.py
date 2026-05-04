from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase100_final_quality_guard"
FOCUSED_TESTS = [
    "scripts/test_phase93_lilim_decomposition_probe.py",
    "scripts/test_phase92b_operator_micro_probe.py",
    "scripts/test_phase92a_live_operator_probe.py",
    "scripts/test_phase99_autonomous_repair_loop.py",
]


REQUIRED_FINAL_METRICS = {
    "acceptedRecombinedCandidates": ">=1",
    "timeWindowViolationCountAfter": "==0",
    "rejectedByCoverage": "==0",
    "rejectedBySlotOverflow": "==0",
    "hardViolations": "==0",
    "antiHardcodeGate": "PASS",
}


def run_command(command: List[str], timeout_s: int) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=timeout_s)
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "runtimeMs": int((time.perf_counter() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "timeout",
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "timeout": True,
        }


def evaluate_final_gate(metrics: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if int(metrics.get("acceptedRecombinedCandidates", 0) or 0) < 1:
        failures.append("acceptedRecombinedCandidates<1")
    if int(metrics.get("timeWindowViolationCountAfter", 0) or 0) != 0:
        failures.append("timeWindowViolationCountAfter>0")
    if int(metrics.get("rejectedByCoverage", 0) or 0) != 0:
        failures.append("rejectedByCoverage>0")
    if int(metrics.get("rejectedBySlotOverflow", 0) or 0) != 0:
        failures.append("rejectedBySlotOverflow>0")
    if int(metrics.get("hardViolations", 0) or 0) != 0:
        failures.append("hardViolations>0")
    if metrics.get("antiHardcodeGate") != "PASS":
        failures.append("antiHardcodeGate!=PASS")
    return {"gate": "PASS" if not failures else "FAIL", "failures": failures, "required": REQUIRED_FINAL_METRICS}


def read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_phase99_probe_summary(loop_output_dir: Path) -> Dict[str, Any] | None:
    loop = read_json(loop_output_dir / "phase99_loop_summary.json")
    if not loop:
        return None
    iterations = loop.get("iterations", [])
    if not iterations:
        return None
    latest_iteration = int(iterations[-1].get("iteration", len(iterations)) or len(iterations))
    return read_json(loop_output_dir / f"iteration_{latest_iteration}" / "phase93_lilim_decomposition_probe_summary.json")


def markdown(summary: Dict[str, Any]) -> str:
    rows = [
        "# Phase 100 Final Quality Guard",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Tests: `{summary.get('testsGate')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        f"- Phase99 loop: `{summary.get('phase99Gate')}`",
        "",
        "## Final Metrics",
        "",
    ]
    for key in REQUIRED_FINAL_METRICS:
        rows.append(f"- `{key}`: `{summary.get('finalMetrics', {}).get(key)}`")
    rows.extend(["", "## Failures", ""])
    failures = summary.get("failures", [])
    if failures:
        rows.extend(f"- `{failure}`" for failure in failures)
    else:
        rows.append("- none")
    rows.append("")
    return "\n".join(rows)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tests = run_command(["py", "-3.13", "-m", "pytest", *FOCUSED_TESTS, "-q"], int(args.test_timeout_s))
    write_json(output_dir / "phase100_tests_command.json", tests)
    anti = run_command(["py", "-3.13", "scripts/run_phase84_antihardcode_guard.py", "--output", str(output_dir / "phase100_antihardcode_report.json")], int(args.guard_timeout_s))
    write_json(output_dir / "phase100_antihardcode_command.json", anti)
    phase99_dir = output_dir / "phase99_autonomous_loop"
    loop = run_command(["py", "-3.13", "scripts/run_phase99_autonomous_repair_loop.py", "--max-iterations", str(args.max_iterations), "--output-dir", str(phase99_dir)], int(args.loop_timeout_s))
    write_json(output_dir / "phase100_phase99_loop_command.json", loop)
    loop_summary = read_json(phase99_dir / "phase99_loop_summary.json") or {}
    final_metrics = latest_phase99_probe_summary(phase99_dir) or {}
    final_gate = evaluate_final_gate(final_metrics)
    failures = list(final_gate["failures"])
    if tests.get("returncode") != 0:
        failures.append("focused-tests-failed")
    if anti.get("returncode") != 0:
        failures.append("anti-hardcode-command-failed")
    if loop.get("returncode") != 0:
        failures.append("phase99-loop-command-failed")
    if not loop_summary:
        failures.append("phase99-loop-summary-missing")
    if not final_metrics:
        failures.append("phase99-final-probe-summary-missing")
    summary = {
        "schemaVersion": "phase100-final-quality-guard/v1",
        "gate": "PASS" if not failures else "FAIL",
        "failures": failures,
        "testsGate": "PASS" if tests.get("returncode") == 0 else "FAIL",
        "antiHardcodeGate": final_metrics.get("antiHardcodeGate"),
        "phase99Gate": loop_summary.get("gate"),
        "phase99Success": loop_summary.get("success"),
        "finalMetrics": final_metrics,
        "requiredFinalMetrics": REQUIRED_FINAL_METRICS,
    }
    write_json(output_dir / "phase100_final_quality_guard_summary.json", summary)
    (output_dir / "phase100_final_quality_guard_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 100 final quality regression guard.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--test-timeout-s", type=int, default=120)
    parser.add_argument("--guard-timeout-s", type=int, default=60)
    parser.add_argument("--loop-timeout-s", type=int, default=240)
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE100 FINAL QUALITY GUARD] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
