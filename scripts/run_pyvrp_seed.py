from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from pyvrp_vrptw_bridge import solve_vrptw


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PyVRP seed contributor for IRX quality benchmark.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=600)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args(argv)

    instance = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = solve_vrptw(instance, args.time_limit_ms, seed=args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[PYVRP SEED] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
