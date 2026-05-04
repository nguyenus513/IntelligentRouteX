from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase99_autonomous_loop_v1"
FOCUSED_TESTS = [
    "scripts/test_phase93_lilim_decomposition_probe.py",
    "scripts/test_phase92b_operator_micro_probe.py",
    "scripts/test_phase92a_live_operator_probe.py",
]


def success(summary: Dict[str, Any]) -> bool:
    return (
        int(summary.get("acceptedRecombinedCandidates", 0) or 0) >= 1
        and int(summary.get("timeWindowViolationCountAfter", 0) or 0) == 0
        and int(summary.get("hardViolations", 0) or 0) == 0
        and int(summary.get("rejectedByCoverage", 0) or 0) == 0
        and int(summary.get("rejectedBySlotOverflow", 0) or 0) == 0
        and summary.get("antiHardcodeGate") == "PASS"
    )


def classify_blocker(summary: Dict[str, Any] | None, tests_ok: bool = True, artifact_written: bool = True) -> str:
    if not tests_ok:
        return "test-fail"
    if summary is None or not artifact_written:
        return "timeout"
    if success(summary):
        return "success"
    if summary.get("antiHardcodeGate") != "PASS":
        return "anti-hardcode-fail"
    if int(summary.get("hardViolations", 0) or 0) > 0:
        return "hard-violation"
    if int(summary.get("rejectedByCoverage", 0) or 0) > 0:
        return "coverage-regression"
    if int(summary.get("rejectedBySlotOverflow", 0) or 0) > 0:
        return "slot-overflow-regression"
    if int(summary.get("timeWindowViolationCountAfter", 0) or 0) > 0 or int(summary.get("rejectedByTimeWindow", 0) or 0) > 0:
        return "time-window-residual"
    if int(summary.get("rejectedByCheckSolution", 0) or 0) > 0:
        return "check-solution-rejected"
    if int(summary.get("acceptedRecombinedCandidates", 0) or 0) == 0:
        return "objective-regression"
    return "check-solution-rejected"


def patch_prompt(iteration: int, blocker: str, summary: Dict[str, Any] | None) -> str:
    summary = summary or {}
    metrics = {
        "iteration": iteration,
        "blocker": blocker,
        "acceptedRecombinedCandidates": summary.get("acceptedRecombinedCandidates"),
        "timeWindowViolationCountBefore": summary.get("timeWindowViolationCountBefore"),
        "timeWindowViolationCountAfter": summary.get("timeWindowViolationCountAfter"),
        "firstViolationNode": summary.get("firstViolationNode"),
        "rejectedByTimeWindow": summary.get("rejectedByTimeWindow"),
        "rejectedByCoverage": summary.get("rejectedByCoverage"),
        "rejectedBySlotOverflow": summary.get("rejectedBySlotOverflow"),
        "hardViolations": summary.get("hardViolations"),
        "antiHardcodeGate": summary.get("antiHardcodeGate"),
        "exactTWFinalizerAttempts": summary.get("exactTWFinalizerAttempts"),
        "exactTWFinalizerImprovements": summary.get("exactTWFinalizerImprovements"),
    }
    return "\n".join([
        "You are modifying IntelligentRouteX.",
        "Current blocker:",
        blocker,
        "Current metrics:",
        json.dumps(metrics, indent=2, sort_keys=True),
        "Goal:",
        "Make Li-Lim decomposition probe reach acceptedRecombinedCandidates >= 1 while preserving all safety gates.",
        "Rules:",
        "- no target-K forcing",
        "- no instance-name or benchmark-name branch",
        "- no comparator/reference/BKS leakage",
        "- no global wall-clock increase",
        "- hardViolations = 0",
        "- rejectedByCoverage = 0",
        "- rejectedBySlotOverflow = 0",
        "- antiHardcodeGate = PASS",
        "Allowed files:",
        "- scripts/optimizer/phase99_exact_tw_route_finalizer.py",
        "- scripts/optimizer/phase98_schedule_feasible_subproblem.py",
        "- scripts/optimizer/phase97_time_window_repair.py",
        "- scripts/run_phase93_lilim_decomposition_probe.py",
        "- scripts/test_phase93_lilim_decomposition_probe.py",
        "- scripts/test_phase99_autonomous_repair_loop.py",
        "Do not touch artifacts/final.",
        "Suggested fix direction:",
        "- Improve exact TW route finalization for affected routes.",
        "- Add bounded permutation/beam search for small affected pair sets.",
        "- Use lexicographic score: hardViolationCount, timeWindowViolationCount, totalLateness, maxLateness, distance.",
        "- Keep route slot count unchanged and preserve exact pickup/dropoff coverage.",
        "Validation commands:",
        "py -3.13 -m pytest scripts/test_phase93_lilim_decomposition_probe.py scripts/test_phase92b_operator_micro_probe.py scripts/test_phase92a_live_operator_probe.py -q",
        "py -3.13 scripts/run_phase93_lilim_decomposition_probe.py --suite li-lim-8case --subproblem-count 1 --request-limit 8 --subproblem-time-limit 5s --hard-wall-clock-ms 30000 --phase97-time-window-after-baseline 10 --output-dir artifacts/benchmark/phase99_validation",
        "",
    ])


def run_command(command: List[str], cwd: Path, timeout_s: int) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, timeout=timeout_s)
        return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout[-12000:], "stderr": completed.stderr[-12000:], "runtimeMs": int((time.perf_counter() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": 124, "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "", "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "timeout", "runtimeMs": int((time.perf_counter() - started) * 1000), "timeout": True}


def run_agent(agent_command: str, prompt: str, cwd: Path, timeout_s: int) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(agent_command, cwd=str(cwd), input=prompt, text=True, capture_output=True, timeout=timeout_s, shell=True)
        return {"command": agent_command, "returncode": completed.returncode, "stdout": completed.stdout[-12000:], "stderr": completed.stderr[-12000:], "runtimeMs": int((time.perf_counter() - started) * 1000)}
    except subprocess.TimeoutExpired as exc:
        return {"command": agent_command, "returncode": 124, "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "", "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "timeout", "runtimeMs": int((time.perf_counter() - started) * 1000), "timeout": True}


def read_summary(iteration_dir: Path) -> Dict[str, Any] | None:
    path = iteration_dir / "phase93_lilim_decomposition_probe_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def markdown(summary: Dict[str, Any]) -> str:
    rows = ["# Phase 99 Autonomous Repair Loop", "", f"- Gate: **{summary.get('gate')}**", f"- Final blocker: `{summary.get('finalBlocker')}`", f"- Iterations: `{summary.get('iterationsRun')}`", f"- Success: `{summary.get('success')}`", ""]
    for item in summary.get("iterations", []):
        rows.append(f"- Iteration `{item.get('iteration')}`: `{item.get('blocker')}` gate=`{item.get('probeGate')}` twAfter=`{item.get('timeWindowViolationCountAfter')}` accepted=`{item.get('acceptedRecombinedCandidates')}`")
    rows.append("")
    return "\n".join(rows)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    iterations = []
    final_blocker = "not-run"
    loop_success = False
    max_seconds = int(args.max_wall_clock_minutes * 60)
    for iteration in range(1, int(args.max_iterations) + 1):
        if time.perf_counter() - started > max_seconds:
            final_blocker = "timeout"
            break
        iteration_dir = output_dir / f"iteration_{iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        test_result = run_command(["py", "-3.13", "-m", "pytest", *FOCUSED_TESTS, "-q"], REPO_ROOT, int(args.test_timeout_s))
        write_json(iteration_dir / "tests_command.json", test_result)
        if test_result["returncode"] != 0:
            blocker = "test-fail"
            prompt = patch_prompt(iteration, blocker, None)
            (iteration_dir / "iteration_patch_prompt.md").write_text(prompt, encoding="utf-8")
            iterations.append({"iteration": iteration, "blocker": blocker, "testsOk": False})
            final_blocker = blocker
            break
        probe_result = run_command([
            "py", "-3.13", "scripts/run_phase93_lilim_decomposition_probe.py",
            "--suite", "li-lim-8case",
            "--subproblem-count", "1",
            "--request-limit", "8",
            "--subproblem-time-limit", "5s",
            "--hard-wall-clock-ms", "30000",
            "--phase97-time-window-after-baseline", "10",
            "--output-dir", str(iteration_dir),
        ], REPO_ROOT, int(args.probe_timeout_s))
        write_json(iteration_dir / "probe_command.json", probe_result)
        summary = read_summary(iteration_dir)
        blocker = classify_blocker(summary, tests_ok=True, artifact_written=summary is not None and probe_result["returncode"] != 124)
        prompt = patch_prompt(iteration, blocker, summary)
        (iteration_dir / "iteration_patch_prompt.md").write_text(prompt, encoding="utf-8")
        item = {
            "iteration": iteration,
            "blocker": blocker,
            "testsOk": True,
            "probeReturnCode": probe_result["returncode"],
            "probeGate": None if summary is None else summary.get("gate"),
            "acceptedRecombinedCandidates": None if summary is None else summary.get("acceptedRecombinedCandidates"),
            "timeWindowViolationCountAfter": None if summary is None else summary.get("timeWindowViolationCountAfter"),
            "hardViolations": None if summary is None else summary.get("hardViolations"),
            "antiHardcodeGate": None if summary is None else summary.get("antiHardcodeGate"),
        }
        iterations.append(item)
        final_blocker = blocker
        if blocker == "success":
            loop_success = True
            break
        if args.agent_command:
            agent_result = run_agent(str(args.agent_command), prompt, REPO_ROOT, int(args.agent_timeout_s))
            write_json(iteration_dir / "agent_command.json", agent_result)
            if agent_result["returncode"] != 0:
                final_blocker = blocker
                break
        else:
            break
    if loop_success:
        gate = "PASS_STRONG"
    elif any(int(item.get("timeWindowViolationCountAfter") or 999999) < 10 for item in iterations) and final_blocker not in {"hard-violation", "coverage-regression", "slot-overflow-regression", "anti-hardcode-fail", "test-fail", "timeout"}:
        gate = "PASS"
    elif final_blocker in {"hard-violation", "coverage-regression", "slot-overflow-regression", "anti-hardcode-fail", "test-fail", "timeout"}:
        gate = "FAIL"
    else:
        gate = "PASS_WITH_LIMITS"
    loop_summary = {"schemaVersion": "phase99-autonomous-repair-loop/v1", "gate": gate, "success": loop_success, "finalBlocker": final_blocker, "iterationsRun": len(iterations), "iterations": iterations, "agentCommandProvided": bool(args.agent_command)}
    write_json(output_dir / "phase99_loop_summary.json", loop_summary)
    (output_dir / "phase99_loop_summary.md").write_text(markdown(loop_summary), encoding="utf-8")
    return loop_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 99 bounded autonomous repair loop.")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--max-wall-clock-minutes", type=float, default=60.0)
    parser.add_argument("--agent-command", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--test-timeout-s", type=int, default=120)
    parser.add_argument("--probe-timeout-s", type=int, default=90)
    parser.add_argument("--agent-timeout-s", type=int, default=900)
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE99 AUTONOMOUS LOOP] {summary['gate']} blocker={summary['finalBlocker']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
