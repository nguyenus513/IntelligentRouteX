from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "real-road-dispatch-v1"
DEFAULT_VISUAL_ROOT = REPO_ROOT / "artifacts" / "visual" / "dispatch-v2" / "real-road-dispatch-v1"


def run(command: Sequence[str]) -> None:
    print("[RUN] " + " ".join(str(part) for part in command))
    subprocess.run(list(command), cwd=REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Real Road Dispatch visual evidence from loop benchmark artifacts.")
    parser.add_argument("--benchmark-root", default=str(DEFAULT_BENCHMARK_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_VISUAL_ROOT))
    parser.add_argument("--scenarios", default="dense-bundle-20x5")
    parser.add_argument("--profiles", default="full-adaptive")
    parser.add_argument("--size", default="XS")
    parser.add_argument("--max-routes", default="8")
    parser.add_argument("--max-orders", default="20")
    parser.add_argument("--max-drivers", default="5")
    parser.add_argument("--single-turn", action="store_true")
    args = parser.parse_args()
    command: List[str] = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_dispatch_v2_visual_evidence.py"),
        "--input-root",
        str(Path(args.benchmark_root)),
        "--output-root",
        str(Path(args.output_root)),
        "--scenarios",
        args.scenarios,
        "--profiles",
        args.profiles,
        "--size",
        args.size,
        "--max-routes",
        args.max_routes,
        "--max-orders",
        args.max_orders,
        "--max-drivers",
        args.max_drivers,
    ]
    if args.single_turn:
        command.append("--single-turn")
    run(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
