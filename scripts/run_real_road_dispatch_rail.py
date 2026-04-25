from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "real-road-dispatch-v1"
DEFAULT_VISUAL_ROOT = REPO_ROOT / "artifacts" / "visual" / "dispatch-v2" / "real-road-dispatch-v1"
STOP_VERDICTS = {"PASS_WITH_LIMITS", "FAIL", "EVIDENCE_GAP"}

LOOP_NAMES = {
    1: "routing-provider-snap-polyline-visual",
    2: "road-aware-generator",
    3: "osrm-table-matrix-cache",
    4: "road-native-sequence-optimizer",
    5: "road-route-quality-classifier",
    6: "ortools-road-native-objective",
    7: "road-aware-plan-repair",
    8: "visual-road-evidence-closure",
}

IMPLEMENTED_LOOPS = {1, 2, 3, 4, 5}

PRESETS = {
    "preset:smoke": {"matrix": "standard-v1", "scenarios": "dense-bundle-20x5", "size": "XS"},
    "preset:quality": {"matrix": "standard-v1", "scenarios": "normal-clear,heavy-rain,traffic-shock,route-ambiguity", "size": "S"},
    "preset:closure": {"matrix": "standard-v1", "scenarios": "normal-clear,heavy-rain,traffic-shock,route-ambiguity,driver-scarcity,dinner-peak-high-density", "size": "S,M"},
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: Sequence[str], env: Dict[str, str] | None = None, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    print("[RUN] " + " ".join(str(part) for part in command))
    completed = subprocess.run(
        list(command),
        cwd=REPO_ROOT,
        env=env,
        text=True,
    )
    if completed.returncode != 0 and not allow_failure:
        raise subprocess.CalledProcessError(completed.returncode, list(command))
    return completed


def profile_name(value: str) -> str:
    if value == "dispatch-v2-full-adaptive":
        return "full-adaptive"
    return value


def env_for_routing(provider: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["IRX_ROUTING_PROVIDER"] = provider
    if provider == "osrm":
        env.setdefault("IRX_ROUTING_BASE_URL", "http://127.0.0.1:5000")
        env.setdefault("IRX_ROUTING_REFINE_LIMIT_PER_TICK", "64")
        env.setdefault("IRX_ROUTING_CONNECT_TIMEOUT_MS", "1000")
        env.setdefault("IRX_ROUTING_READ_TIMEOUT_MS", "3000")
    return env


def write_loop_manifest(loop_dir: Path, loop: int, args: argparse.Namespace, preset: Dict[str, str], status: str = "STARTED", blockers: List[str] | None = None) -> Path:
    payload = {
        "schemaVersion": "real-road-loop-manifest/v1",
        "loop": loop,
        "loopName": LOOP_NAMES.get(loop, "unknown"),
        "status": status,
        "blockers": blockers or [],
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "routingProvider": args.routing_provider,
        "profile": args.profile,
        "matrixPreset": args.matrix,
        "benchmarkPreset": preset,
    }
    path = loop_dir / "loop_manifest.json"
    write_json(path, payload)
    return path


def update_manifest(path: Path, **updates: Any) -> None:
    payload = read_json(path) if path.exists() else {}
    payload.update(updates)
    payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(path, payload)


def update_rail_state(output_root: Path, loop: int, verdict: str, reasons: List[str], complete: bool = False) -> None:
    state = {
        "schemaVersion": "real-road-dispatch-rail-state/v1",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "currentLoop": loop,
        "currentLoopName": LOOP_NAMES.get(loop, "unknown"),
        "lastVerdict": verdict,
        "lastReasons": reasons,
        "complete": complete,
    }
    write_json(output_root / "rail_state.json", state)


def run_benchmark_visual_metrics(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path, loop: int) -> Tuple[str, List[str]]:
    benchmark_root = loop_dir / "benchmark"
    visual_root = loop_dir / "visual"
    env = env_for_routing(args.routing_provider)
    run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_dispatch_v2_standard_comparison.py"),
        "--matrix",
        preset["matrix"],
        "--profiles",
        profile_name(args.profile),
        "--scenarios",
        preset["scenarios"],
        "--size",
        preset["size"],
        "--output-root",
        str(benchmark_root),
        "--skip-llm-preflight",
    ], env=env)
    run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "render_real_road_visual.py"),
        "--benchmark-root",
        str(benchmark_root),
        "--output-root",
        str(visual_root),
        "--scenarios",
        preset["scenarios"].split(",")[0],
        "--profiles",
        profile_name(args.profile),
        "--size",
        preset["size"].split(",")[0],
        "--single-turn",
    ])
    metrics_path = loop_dir / "metrics.json"
    gate_path = loop_dir / "gate_result.json"
    run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "build_real_road_metrics.py"),
        "--benchmark-root",
        str(benchmark_root),
        "--visual-root",
        str(visual_root),
        "--output",
        str(metrics_path),
    ])
    gate_completed = run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "evaluate_real_road_loop_gate.py"),
        "--loop",
        str(loop),
        "--metrics",
        str(metrics_path),
        "--output",
        str(gate_path),
        "--provider-ready",
    ], allow_failure=True)
    run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "write_real_road_loop_report.py"),
        "--metrics",
        str(metrics_path),
        "--gate",
        str(gate_path),
        "--manifest",
        str(manifest_path),
        "--output",
        str(loop_dir / "routePlanQualityLoopReport.md"),
    ])
    gate = read_json(gate_path)
    return str(gate.get("verdict", "FAIL")), list(gate.get("reasons", []))


def run_loop_1(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path) -> Tuple[str, List[str]]:
    return run_benchmark_visual_metrics(loop_dir, args, preset, manifest_path, 1)


def run_loop_2(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path) -> Tuple[str, List[str]]:
    return run_benchmark_visual_metrics(loop_dir, args, preset, manifest_path, 2)


def run_loop_3(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path) -> Tuple[str, List[str]]:
    return run_benchmark_visual_metrics(loop_dir, args, preset, manifest_path, 3)


def run_loop_4(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path) -> Tuple[str, List[str]]:
    return run_benchmark_visual_metrics(loop_dir, args, preset, manifest_path, 4)


def run_loop_5(loop_dir: Path, args: argparse.Namespace, preset: Dict[str, str], manifest_path: Path) -> Tuple[str, List[str]]:
    return run_benchmark_visual_metrics(loop_dir, args, preset, manifest_path, 5)


def run_unimplemented_loop(loop_dir: Path, loop: int, manifest_path: Path) -> Tuple[str, List[str]]:
    reasons = [f"loop-{loop:02d}-{LOOP_NAMES.get(loop, 'unknown')}-implementation-not-yet-wired"]
    metrics_path = loop_dir / "metrics.json"
    gate_path = loop_dir / "gate_result.json"
    write_json(metrics_path, {"schemaVersion": "real-road-dispatch-metrics/v1", "loop": loop, "blockers": reasons})
    write_json(gate_path, {"schemaVersion": "real-road-loop-gate/v1", "loop": loop, "verdict": "EVIDENCE_GAP", "reasons": reasons})
    run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "write_real_road_loop_report.py"),
        "--metrics",
        str(metrics_path),
        "--gate",
        str(gate_path),
        "--manifest",
        str(manifest_path),
        "--output",
        str(loop_dir / "routePlanQualityLoopReport.md"),
    ])
    return "EVIDENCE_GAP", reasons


def run_loop(loop: int, args: argparse.Namespace, preset: Dict[str, str]) -> Tuple[str, List[str]]:
    output_root = Path(args.output_root)
    loop_dir = output_root / f"loop-{loop:02d}"
    loop_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_loop_manifest(loop_dir, loop, args, preset)
    if loop in IMPLEMENTED_LOOPS:
        if loop == 1:
            verdict, reasons = run_loop_1(loop_dir, args, preset, manifest_path)
        elif loop == 2:
            verdict, reasons = run_loop_2(loop_dir, args, preset, manifest_path)
        elif loop == 3:
            verdict, reasons = run_loop_3(loop_dir, args, preset, manifest_path)
        elif loop == 4:
            verdict, reasons = run_loop_4(loop_dir, args, preset, manifest_path)
        elif loop == 5:
            verdict, reasons = run_loop_5(loop_dir, args, preset, manifest_path)
        else:
            verdict, reasons = run_unimplemented_loop(loop_dir, loop, manifest_path)
    else:
        verdict, reasons = run_unimplemented_loop(loop_dir, loop, manifest_path)
    status = "PASS" if verdict == "PASS" else "BLOCKED"
    update_manifest(manifest_path, status=status, verdict=verdict, reasons=reasons, completedAt=datetime.now(timezone.utc).isoformat())
    update_rail_state(output_root, loop, verdict, reasons, complete=(loop == 8 and verdict == "PASS"))
    return verdict, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Real Road Dispatch Optimization Rail state machine.")
    parser.add_argument("--start-loop", type=int, default=1)
    parser.add_argument("--target-loop", type=int, default=1)
    parser.add_argument("--auto-advance", action="store_true")
    parser.add_argument("--profile", default="dispatch-v2-full-adaptive")
    parser.add_argument("--routing-provider", choices=("synthetic", "osrm", "tomtom"), default="osrm")
    parser.add_argument("--matrix", choices=tuple(PRESETS.keys()), default="preset:smoke")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()

    preset = PRESETS[args.matrix]
    current = args.start_loop
    target = args.target_loop
    while current <= target:
        print(f"[REAL ROAD LOOP START] loop={current:02d} {LOOP_NAMES.get(current, 'unknown')}")
        verdict, reasons = run_loop(current, args, preset)
        print(f"[REAL ROAD LOOP DONE] loop={current:02d} verdict={verdict} reasons={reasons}")
        if verdict != "PASS":
            return 2
        if not args.auto_advance:
            return 0
        current += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

