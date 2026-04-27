from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "elite-closure-loop"
DEFAULT_ELITE_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "elite-food-dispatch-intelligence"


@dataclass(frozen=True)
class Phase:
    sprint: str
    phase: str
    goal: str
    commands: tuple[tuple[str, ...], ...]
    timeout_seconds: int
    required: bool = True


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def python_cmd(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


def phases(profile: str, output_root: Path) -> List[Phase]:
    academic_time = "20s" if profile == "smoke" else "30m"
    academic_timeout = 90 if profile == "smoke" else 7200
    route_pairs = "20" if profile == "smoke" else "50"
    certification_level = "smoke" if profile == "smoke" else "core"
    certification_timeout = 300 if profile == "smoke" else 3600
    return [
        Phase(
            sprint="Sprint 1 - Academic Quality",
            phase="academic-max-quality-v5",
            goal="Reduce vehicle-count gap with route merge, route elimination, cross-exchange, and set partitioning.",
            commands=(
                python_cmd(
                    "scripts/run_academic_max_quality.py",
                    "--instances", "C1_10_1,R1_10_1,RC1_10_1",
                    "--time-limit", academic_time,
                    "--or-tools-runs", "2" if profile == "smoke" else "6",
                    "--operator-intensity", "1" if profile == "smoke" else "2",
                    "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "academic-objective-quality-v5"),
                ),
            ),
            timeout_seconds=academic_timeout,
        ),
        Phase(
            sprint="Sprint 2 - Traffic And Route Beauty",
            phase="traffic-aware-route-quality",
            goal="Rerun community traffic route benchmark after public data closure.",
            commands=(python_cmd("scripts/run_community_traffic_route_benchmark.py", "--pairs", route_pairs, "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "community-traffic-route")),),
            timeout_seconds=300,
        ),
        Phase(
            sprint="Sprint 2 - Traffic And Route Beauty",
            phase="shape-aware-route-beauty",
            goal="Rerun multi-region DIMACS route beauty benchmark.",
            commands=(python_cmd("scripts/run_route_beauty_benchmark.py", "--regions", "NY,BAY,COL,FLA", "--pairs", route_pairs, "--node-limit", "20000", "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "route-beauty-community")),),
            timeout_seconds=300,
        ),
        Phase(
            sprint="Sprint 3 - ML Value",
            phase="ml-ablation-value",
            goal="Rerun ML evidence rail with RL4CO/Torch importability and adapter status.",
            commands=(python_cmd("scripts/run_ml_intelligence_benchmark.py", "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "ml-intelligence-community")),),
            timeout_seconds=120,
        ),
        Phase(
            sprint="Sprint 4 - Food Driver Sequence Quality",
            phase="food-driver-sequence-quality",
            goal="Rerun external certification suite to refresh MDRPLib, driver, anchor, sequence, and order-to-delivery evidence.",
            commands=(python_cmd("scripts/run_dispatch_benchmark_certification_suite.py", "--level", certification_level, "--external-only", "--time-limit", "30s", "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "certification-suite-external-only-full"), "--emit-scorecard"),),
            timeout_seconds=certification_timeout,
        ),
        Phase(
            sprint="Sprint 5 - Dynamic And Stochastic",
            phase="dynamic-rolling-horizon-quality",
            goal="Refresh ICAPS/DPDP dynamic certification rows and continuity checks.",
            commands=(python_cmd("scripts/run_dispatch_benchmark_certification_suite.py", "--level", "smoke", "--external-only", "--time-limit", "30s", "--output-root", str(output_root / "dynamic-refresh")),),
            timeout_seconds=300,
            required=False,
        ),
        Phase(
            sprint="Sprint 5 - Dynamic And Stochastic",
            phase="stochastic-community-coverage",
            goal="Verify public dataset readiness and keep missing stochastic benchmark evidence explicit.",
            commands=(python_cmd("scripts/verify_certification_dataset.py", "--level", "full"),),
            timeout_seconds=120,
            required=False,
        ),
        Phase(
            sprint="Final - Scorecard",
            phase="elite-scorecard-and-gap-plan",
            goal="Rebuild Elite scorecard and gap closure plan from all refreshed artifacts.",
            commands=(
                python_cmd("scripts/run_elite_food_dispatch_benchmark.py", "--output-root", str(DEFAULT_ELITE_ROOT)),
                python_cmd("scripts/build_elite_gap_closure_plan.py", "--output-root", str(REPO_ROOT / "artifacts" / "benchmark" / "elite-gap-closure")),
            ),
            timeout_seconds=180,
        ),
    ]


def run_command(command: Sequence[str], timeout_seconds: int) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=timeout_seconds)
        return {
            "command": list(command),
            "returnCode": completed.returncode,
            "runtimeSeconds": round(time.perf_counter() - started, 3),
            "stdoutTail": completed.stdout[-4000:],
            "stderrTail": completed.stderr[-4000:],
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "returnCode": 124,
            "runtimeSeconds": round(time.perf_counter() - started, 3),
            "stdoutTail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderrTail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timedOut": True,
        }


def run_phase(phase: Phase) -> Dict[str, Any]:
    command_results = [run_command(command, phase.timeout_seconds) for command in phase.commands]
    ok = all(result["returnCode"] == 0 for result in command_results)
    return {
        "sprint": phase.sprint,
        "phase": phase.phase,
        "goal": phase.goal,
        "required": phase.required,
        "ok": ok,
        "commands": command_results,
    }


def scaled_phase(phase: Phase, scale: float) -> Phase:
    return Phase(
        sprint=phase.sprint,
        phase=phase.phase,
        goal=phase.goal,
        commands=phase.commands,
        timeout_seconds=max(1, int(phase.timeout_seconds * scale)),
        required=phase.required,
    )


def final_status() -> Dict[str, Any]:
    elite_path = DEFAULT_ELITE_ROOT / "elite_results.json"
    if not elite_path.exists():
        return {"eliteAvailable": False}
    elite = read_json(elite_path)
    return {
        "eliteAvailable": True,
        "finalVerdict": elite.get("finalVerdict"),
        "overallScore": elite.get("overallScore"),
        "mainBlockers": elite.get("mainBlockers", []),
        "blockerCount": len(elite.get("mainBlockers", [])),
    }


def markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Elite Closure Loop Report",
        "",
        f"PROFILE = {result['profile']}",
        f"FINAL_VERDICT = {result['finalStatus'].get('finalVerdict')}",
        f"OVERALL_SCORE = {float(result['finalStatus'].get('overallScore') or 0.0):.3f}",
        f"BLOCKER_COUNT = {result['finalStatus'].get('blockerCount')}",
        "",
        "| Sprint | Phase | OK | Required |",
        "| --- | --- | ---: | ---: |",
    ]
    for phase in result["phases"]:
        lines.append(f"| {phase['sprint']} | `{phase['phase']}` | `{phase['ok']}` | `{phase['required']}` |")
    lines.extend(["", "## Remaining Blockers", ""])
    for blocker in result["finalStatus"].get("mainBlockers", []):
        lines.append(f"- `{blocker}`")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 8-phase / 5-sprint Elite benchmark closure loop.")
    parser.add_argument("--profile", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--phase-timeout-scale", type=float, default=1.0)
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    results = []
    for phase in phases(args.profile, output_root):
        results.append(run_phase(scaled_phase(phase, args.phase_timeout_scale)))
        partial = {
            "schemaVersion": "elite-closure-loop/v1",
            "profile": args.profile,
            "complete": False,
            "phases": results,
            "finalStatus": final_status(),
        }
        write_json(output_root / "closure_loop_results.json", partial)
        (output_root / "closure_loop_report.md").write_text(markdown(partial), encoding="utf-8")
    result = {
        "schemaVersion": "elite-closure-loop/v1",
        "profile": args.profile,
        "complete": True,
        "phases": results,
        "finalStatus": final_status(),
    }
    write_json(output_root / "closure_loop_results.json", result)
    (output_root / "closure_loop_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[ELITE CLOSURE LOOP JSON] {output_root / 'closure_loop_results.json'}")
    print(f"[ELITE CLOSURE LOOP REPORT] {output_root / 'closure_loop_report.md'}")
    required_failed = any(not phase["ok"] and phase["required"] for phase in results)
    return 1 if required_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
