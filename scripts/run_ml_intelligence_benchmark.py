from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "ml-intelligence-community"
SERVICES_ROOT = REPO_ROOT / "services"
DEFAULT_ABLATION_ROOT = REPO_ROOT / "artifacts" / "benchmark"


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


def probe_worker_readiness(service_name: str, timeout_seconds: int = 20) -> Dict[str, Any]:
    app_path = SERVICES_ROOT / service_name / "app.py"
    if not app_path.exists():
        return {"ready": False, "reason": "worker-app-missing", "version": {}}
    probe = """
import importlib.util
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('worker_app', path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
if not hasattr(module, '_readiness'):
    print(json.dumps({'ready': False, 'reason': 'readiness-function-missing', 'version': {}}))
else:
    ready, reason, _manifest, _artifact, version = module._readiness()
    print(json.dumps({'ready': bool(ready), 'reason': reason, 'version': version}))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe, str(app_path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ready": False, "reason": "worker-readiness-timeout", "version": {}}
    if completed.returncode != 0:
        return {"ready": False, "reason": "worker-readiness-error", "stderr": completed.stderr[-500:], "version": {}}
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        return {"ready": False, "reason": "worker-readiness-invalid-output", "error": str(exc), "version": {}}


def local_adapter_status() -> Dict[str, Any]:
    routefinder_present = service_present("ml-routefinder-worker")
    greedrl_present = service_present("ml-greedrl-worker")
    forecast_present = service_present("ml-forecast-worker")
    tabular_present = service_present("ml-tabular-worker")
    routefinder_probe = probe_worker_readiness("ml-routefinder-worker") if routefinder_present else {"ready": False, "reason": "worker-app-missing", "version": {}}
    greedrl_probe = probe_worker_readiness("ml-greedrl-worker") if greedrl_present else {"ready": False, "reason": "worker-app-missing", "version": {}}
    forecast_probe = probe_worker_readiness("ml-forecast-worker", timeout_seconds=90) if forecast_present else {"ready": False, "reason": "worker-app-missing", "version": {}}
    worker_readiness_audited = routefinder_present and greedrl_present and forecast_present
    worker_implementations = {
        "routeFinderWorkerImplementationPresent": routefinder_present,
        "greedRlWorkerImplementationPresent": greedrl_present,
        "forecastWorkerImplementationPresent": forecast_present,
        "tabularWorkerImplementationPresent": tabular_present,
    }
    return {
        **worker_implementations,
        "localMlPolicyAdapterPresent": routefinder_present and greedrl_present and forecast_present,
        "routeFinderWorkerReady": bool(routefinder_probe.get("ready")),
        "greedRlWorkerReady": bool(greedrl_probe.get("ready")),
        "forecastWorkerReady": bool(forecast_probe.get("ready")),
        "workerReadinessAudited": worker_readiness_audited,
        "workerReadinessReason": "live-readiness-probes-completed" if worker_readiness_audited else "worker-implementation-missing",
        "workerReadinessDetails": {
            "routefinder": routefinder_probe,
            "greedrl": greedrl_probe,
            "forecast": forecast_probe,
        },
        "greedRlRuntimeMode": greedrl_runtime_mode(),
    }


def ml_ablation_rows(ablation_root: Path = DEFAULT_ABLATION_ROOT) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not ablation_root.exists():
        return rows
    for path in sorted(ablation_root.rglob("dispatch-quality-ablation*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        component = payload.get("toggledComponent")
        if component not in {"routefinder", "greedrl", "forecast", "tabular"}:
            continue
        control = payload.get("controlMetrics", {})
        variant = payload.get("variantMetrics", {})
        control_utility = float(control.get("robustUtilityAverage", 0.0) or 0.0)
        variant_utility = float(variant.get("robustUtilityAverage", 0.0) or 0.0)
        control_objective = float(control.get("selectorObjectiveValue", 0.0) or 0.0)
        variant_objective = float(variant.get("selectorObjectiveValue", 0.0) or 0.0)
        rows.append({
            "component": component,
            "scenarioPack": payload.get("scenarioPack"),
            "workloadSize": payload.get("workloadSize"),
            "executionMode": payload.get("executionMode"),
            "robustUtilityDelta": control_utility - variant_utility,
            "selectorObjectiveDelta": control_objective - variant_objective,
            "artifactPath": str(path),
        })
    return rows


def ml_value_evidence(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    positive_rows = [row for row in rows if float(row.get("robustUtilityDelta", 0.0)) > 0.0 or float(row.get("selectorObjectiveDelta", 0.0)) > 0.0]
    positive_components = sorted({str(row.get("component")) for row in positive_rows})
    return {
        "mlAblationArtifactCount": len(rows),
        "mlPositiveAblationCount": len(positive_rows),
        "mlPositiveComponents": positive_components,
        "mlAblationRows": list(rows[:20]),
        "mlValueProven": len(positive_components) >= 2,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_benchmark() -> Dict[str, Any]:
    rl4co_status = package_status("rl4co")
    torch_status = package_status("torch")
    cuda = torch_cuda_status(torch_status)
    adapter = local_adapter_status()
    value_evidence = ml_value_evidence(ml_ablation_rows())
    common = {
        "torchAvailable": torch_status["available"],
        "torchImportable": torch_status["importable"],
        "torchVersion": torch_status.get("version"),
        **cuda,
        **adapter,
        **value_evidence,
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
    reasons = [] if value_evidence["mlValueProven"] else ["ml-value-not-proven"]
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
