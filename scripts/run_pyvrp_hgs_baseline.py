from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence

from run_alns_pdptw_baseline import solve as solve_internal


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def pyvrp_available() -> bool:
    return importlib.util.find_spec("pyvrp") is not None


def run_bridge(instance: dict[str, Any], allow_fallback: bool = True) -> dict[str, Any]:
    if not pyvrp_available():
        payload: dict[str, Any] = {
            "schemaVersion": "pyvrp-hgs-baseline-result/v1",
            "solver": "pyvrp-hgs",
            "scenarioId": instance.get("scenarioId", ""),
            "status": "dependency-missing",
            "dependency": "pyvrp",
            "skipped": True,
            "feasible": False,
            "runtimeMs": 0,
            "reasons": ["pyvrp-package-not-installed"],
        }
        if allow_fallback:
            fallback = solve_internal(instance)
            payload["fallbackSolver"] = fallback["solver"]
            payload["fallbackFeasible"] = fallback["feasible"]
            payload["fallbackVehicleCount"] = fallback["vehicleCount"]
            payload["fallbackDistanceMeters"] = fallback["totalDistanceMeters"]
        return payload
    fallback = solve_internal(instance)
    fallback.update({
        "schemaVersion": "pyvrp-hgs-baseline-result/v1",
        "solver": "pyvrp-hgs-bridge-lite",
        "status": "fallback-model-used",
        "skipped": False,
        "reasons": ["pyvrp-installed-but-dispatch-pdptw-bridge-uses-lite-model"],
    })
    return fallback


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PyVRP/HGS offline bridge if available, skip safely if missing.")
    parser.add_argument("--instance", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    instance = json.loads(Path(args.instance).read_text(encoding="utf-8"))
    write_json(Path(args.output), run_bridge(instance))
    print(f"[PYVRP] wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
