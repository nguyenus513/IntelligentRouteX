from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_DIR = REPO_ROOT / "benchmarks" / "suites"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase61-suite-registry-v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_suite(name: str, suite_dir: Path = SUITE_DIR) -> Dict[str, Any]:
    manifest_path = suite_dir / f"{name}.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Unknown benchmark suite: {name}")
    manifest = read_json(manifest_path)
    if manifest.get("suite") != name:
        raise ValueError(f"Suite manifest name mismatch: {manifest_path}")
    if not manifest.get("instances"):
        raise ValueError(f"Suite manifest has no instances: {manifest_path}")
    return manifest


def list_suites(suite_dir: Path = SUITE_DIR) -> List[Dict[str, Any]]:
    return [read_json(path) for path in sorted(suite_dir.glob("*.json"))]


def build_registry(selected_suite: str | None = None) -> Dict[str, Any]:
    manifests = [load_suite(selected_suite)] if selected_suite else list_suites()
    return {
        "schemaVersion": "phase61-benchmark-suite-registry/v1",
        "suiteCount": len(manifests),
        "suites": manifests,
    }


def markdown(registry: Dict[str, Any]) -> str:
    lines = ["# Phase 61 Benchmark Suite Registry", "", "| Suite | Source | Problem | Instances |", "|---|---|---|---:|"]
    for suite in registry.get("suites", []):
        lines.append(f"| {suite.get('suite')} | {suite.get('source')} | {suite.get('problemType')} | {len(suite.get('instances', []))} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize benchmark suite manifests for Phase 61.")
    parser.add_argument("--suite", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    registry = build_registry(args.suite or None)
    output_dir = Path(args.output_dir)
    write_json(output_dir / "phase61_benchmark_suite_registry.json", registry)
    (output_dir / "phase61_benchmark_suite_registry.md").parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase61_benchmark_suite_registry.md").write_text(markdown(registry), encoding="utf-8")
    print(f"[PHASE61 BENCHMARK SUITE REGISTRY] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
