from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "ml-intelligence-community"


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def package_status(name: str) -> Dict[str, Any]:
    if not package_available(name):
        return {"available": False, "importable": False, "version": None}
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return {"available": True, "importable": False, "version": None, "importError": str(exc)}
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = getattr(module, "__version__", None)
    return {"available": True, "importable": True, "version": version}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_benchmark() -> Dict[str, Any]:
    rl4co_status = package_status("rl4co")
    torch_status = package_status("torch")
    if not rl4co_status["available"]:
        return {
            "schemaVersion": "ml-intelligence-community/v1",
            "benchmarkFamily": "rl4co",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["rl4co-package-not-installed", "our-ml-policy-adapter-missing"],
            "rl4coAvailable": False,
            "rl4coImportable": False,
            "rl4coVersion": None,
            "torchAvailable": torch_status["available"],
            "torchImportable": torch_status["importable"],
            "torchVersion": torch_status.get("version"),
            "mlValueProven": False,
        }
    if not rl4co_status["importable"]:
        return {
            "schemaVersion": "ml-intelligence-community/v1",
            "benchmarkFamily": "rl4co",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["rl4co-package-installed-but-not-importable", "our-ml-policy-adapter-missing"],
            "rl4coAvailable": True,
            "rl4coImportable": False,
            "rl4coVersion": rl4co_status.get("version"),
            "rl4coImportError": rl4co_status.get("importError"),
            "torchAvailable": torch_status["available"],
            "torchImportable": torch_status["importable"],
            "torchVersion": torch_status.get("version"),
            "mlValueProven": False,
        }
    return {
        "schemaVersion": "ml-intelligence-community/v1",
        "benchmarkFamily": "rl4co",
        "finalVerdict": "PASS_WITH_LIMITS",
        "verdictReasons": ["rl4co-installed-but-policy-adapter-pending"],
        "rl4coAvailable": True,
        "rl4coImportable": True,
        "rl4coVersion": rl4co_status.get("version"),
        "torchAvailable": torch_status["available"],
        "torchImportable": torch_status["importable"],
        "torchVersion": torch_status.get("version"),
        "mlValueProven": False,
    }


def markdown(result: Dict[str, Any]) -> str:
    return "\n".join([
        "# ML Intelligence Community Benchmark",
        "",
        f"FINAL_VERDICT = {result['finalVerdict']}",
        "",
        f"- benchmark family: `{result['benchmarkFamily']}`",
        f"- RL4CO available: `{result['rl4coAvailable']}`",
        f"- RL4CO importable: `{result.get('rl4coImportable')}`",
        f"- RL4CO version: `{result.get('rl4coVersion')}`",
        f"- torch available: `{result['torchAvailable']}`",
        f"- torch importable: `{result.get('torchImportable')}`",
        f"- torch version: `{result.get('torchVersion')}`",
        f"- ML value proven: `{result['mlValueProven']}`",
        f"- reasons: `{', '.join(result.get('verdictReasons', []))}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run community ML intelligence benchmark evidence rail.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = run_benchmark()
    write_json(output_root / "ml_intelligence_results.json", result)
    (output_root / "ml_intelligence_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[ML INTELLIGENCE JSON] {output_root / 'ml_intelligence_results.json'}")
    print(f"[ML INTELLIGENCE REPORT] {output_root / 'ml_intelligence_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
