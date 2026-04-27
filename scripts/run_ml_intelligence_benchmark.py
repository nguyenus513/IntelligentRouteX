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
SERVICES_ROOT = REPO_ROOT / "services"


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


def torch_cuda_status(torch_status: Dict[str, Any]) -> Dict[str, Any]:
    if not torch_status.get("importable"):
        return {"torchCudaAvailable": False, "torchCudaDeviceCount": 0, "torchCudaDeviceNames": []}
    try:
        torch = importlib.import_module("torch")
        available = bool(torch.cuda.is_available())
        count = int(torch.cuda.device_count()) if available else 0
        names = [str(torch.cuda.get_device_name(index)) for index in range(count)] if available else []
    except Exception as exc:
        return {"torchCudaAvailable": False, "torchCudaDeviceCount": 0, "torchCudaDeviceNames": [], "torchCudaProbeError": str(exc)}
    return {"torchCudaAvailable": available, "torchCudaDeviceCount": count, "torchCudaDeviceNames": names}


def service_present(name: str) -> bool:
    return (SERVICES_ROOT / name / "app.py").exists()


def greedrl_runtime_mode() -> str:
    adapter_path = SERVICES_ROOT / "ml-greedrl-worker" / "greedrl_runtime_adapter.py"
    if not adapter_path.exists():
        return "missing"
    source = adapter_path.read_text(encoding="utf-8", errors="ignore")
    if "greedrl-native-runtime" in source and "greedrl-lite-runtime" in source:
        return "native-or-lite-configured"
    if "greedrl-native-runtime" in source:
        return "native-configured"
    if "greedrl-lite-runtime" in source:
        return "lite-configured"
    return "unknown"


def local_adapter_status() -> Dict[str, Any]:
    routefinder_present = service_present("ml-routefinder-worker")
    greedrl_present = service_present("ml-greedrl-worker")
    forecast_present = service_present("ml-forecast-worker")
    tabular_present = service_present("ml-tabular-worker")
    worker_implementations = {
        "routeFinderWorkerImplementationPresent": routefinder_present,
        "greedRlWorkerImplementationPresent": greedrl_present,
        "forecastWorkerImplementationPresent": forecast_present,
        "tabularWorkerImplementationPresent": tabular_present,
    }
    return {
        **worker_implementations,
        "localMlPolicyAdapterPresent": routefinder_present and greedrl_present and forecast_present,
        "routeFinderWorkerReady": False,
        "greedRlWorkerReady": False,
        "forecastWorkerReady": False,
        "workerReadinessAudited": False,
        "workerReadinessReason": "static-filesystem-audit-only-no-live-worker-healthcheck-run",
        "greedRlRuntimeMode": greedrl_runtime_mode(),
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_benchmark() -> Dict[str, Any]:
    rl4co_status = package_status("rl4co")
    torch_status = package_status("torch")
    cuda = torch_cuda_status(torch_status)
    adapter = local_adapter_status()
    common = {
        "torchAvailable": torch_status["available"],
        "torchImportable": torch_status["importable"],
        "torchVersion": torch_status.get("version"),
        **cuda,
        **adapter,
        "mlValueProven": False,
    }
    if not rl4co_status["available"]:
        return {
            "schemaVersion": "ml-intelligence-community/v1",
            "benchmarkFamily": "rl4co",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["rl4co-package-not-installed", "ml-value-not-proven"],
            "rl4coAvailable": False,
            "rl4coImportable": False,
            "rl4coVersion": None,
            **common,
        }
    if not rl4co_status["importable"]:
        return {
            "schemaVersion": "ml-intelligence-community/v1",
            "benchmarkFamily": "rl4co",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["rl4co-package-installed-but-not-importable", "ml-value-not-proven"],
            "rl4coAvailable": True,
            "rl4coImportable": False,
            "rl4coVersion": rl4co_status.get("version"),
            "rl4coImportError": rl4co_status.get("importError"),
            **common,
        }
    reasons = ["ml-value-not-proven"]
    if not adapter["workerReadinessAudited"]:
        reasons.append("ml-worker-readiness-not-audited")
    return {
        "schemaVersion": "ml-intelligence-community/v1",
        "benchmarkFamily": "rl4co",
        "finalVerdict": "PASS_WITH_LIMITS",
        "verdictReasons": reasons,
        "rl4coAvailable": True,
        "rl4coImportable": True,
        "rl4coVersion": rl4co_status.get("version"),
        **common,
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
        f"- torch CUDA available: `{result.get('torchCudaAvailable')}`",
        f"- torch CUDA device count: `{result.get('torchCudaDeviceCount')}`",
        f"- local ML policy adapter present: `{result.get('localMlPolicyAdapterPresent')}`",
        f"- RouteFinder worker ready: `{result.get('routeFinderWorkerReady')}`",
        f"- GreedRL worker ready: `{result.get('greedRlWorkerReady')}`",
        f"- Forecast worker ready: `{result.get('forecastWorkerReady')}`",
        f"- GreedRL runtime mode: `{result.get('greedRlRuntimeMode')}`",
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
