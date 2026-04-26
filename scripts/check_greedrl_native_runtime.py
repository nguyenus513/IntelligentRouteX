from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "services" / "ml-greedrl-worker" / "app.py"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "benchmark" / "full-system-e2e" / "greedrl_native_runtime_report.json"


def _manifest_value_for_greedrl(key: str) -> str | None:
    manifest_path = Path(os.getenv("IRX_MODEL_MANIFEST_PATH", REPO_ROOT / "services" / "models" / "model-manifest.yaml"))
    if not manifest_path.exists():
        return None
    in_greedrl = False
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("- worker_name:"):
            in_greedrl = stripped.split(":", 1)[1].strip() == "ml-greedrl-worker"
            continue
        if in_greedrl and stripped.startswith(f"{key}:"):
            value = stripped.split(":", 1)[1].strip().strip('"')
            candidate = Path(value)
            if candidate.is_absolute():
                return str(candidate)
            return str((manifest_path.parent / candidate).resolve())
    return None


def _runtime_manifest_path() -> Path:
    override = os.getenv("IRX_GREEDRL_RUNTIME_MANIFEST", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    manifest_value = _manifest_value_for_greedrl("local_artifact_path")
    if manifest_value:
        return Path(manifest_value)
    return REPO_ROOT / "services" / "models" / "materialized" / "greedrl" / "model" / "greedrl-runtime-manifest.json"


def _runtime_python(runtime_manifest: dict[str, Any]) -> Path:
    override = os.getenv("IRX_GREEDRL_RUNTIME_PYTHON", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    value = runtime_manifest.get("runtimePythonExecutable")
    if value:
        return Path(value).expanduser().resolve()
    return Path(sys.executable).resolve()


def _runtime_env(runtime_manifest: dict[str, Any], runtime_manifest_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("IRX_GREEDRL_RUNTIME_MODE", None)
    module_root = runtime_manifest.get("runtimeModuleRoot")
    if module_root:
        module_path = (runtime_manifest_path.parent / module_root).resolve()
        env["PYTHONPATH"] = str(module_path) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env

def classify_failure(stderr: str, stdout: str) -> str:
    text = f"{stderr}\n{stdout}"
    if "WinError 4551" in text or "Application Control policy" in text or "torch_python.dll" in text:
        return "WINDOWS_APPLICATION_CONTROL_BLOCKED_TORCH_DLL"
    if "No module named 'greedrl'" in text or "No module named 'greedrl_c'" in text:
        return "GREEDRL_NATIVE_MODULE_MISSING"
    if "loaded-model-fingerprint-mismatch" in text:
        return "MODEL_FINGERPRINT_MISMATCH"
    if "unsupported-action" in text:
        return "RUNTIME_ADAPTER_CONTRACT_ERROR"
    if "TimeoutExpired" in text:
        return "GREEDRL_NATIVE_RUNTIME_TIMEOUT"
    return "UNKNOWN_NATIVE_RUNTIME_FAILURE"


def run_native_probe() -> dict[str, Any]:
    runtime_manifest_path = _runtime_manifest_path()
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    runtime_python = _runtime_python(runtime_manifest)
    runtime_env = _runtime_env(runtime_manifest, runtime_manifest_path)
    adapter_path = APP_PATH.parent / "greedrl_runtime_adapter.py"
    request = {"action": "self-check", "payload": {}}
    command = [str(runtime_python), str(adapter_path), "--runtime-manifest", str(runtime_manifest_path)]
    completed = subprocess.run(
        command,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        env=runtime_env,
        timeout=30,
    )
    ok = completed.returncode == 0
    payload: dict[str, Any] | None = None
    if ok:
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            ok = False
    failure_class = None if ok else classify_failure(completed.stderr, completed.stdout)
    verdict = "PASS" if ok and payload and payload.get("runtimeMode") == "native" else "BLOCKED"
    return {
        "schemaVersion": "greedrl-native-runtime-probe/v1",
        "verdict": verdict,
        "runtimeModeRequested": "native",
        "runtimePython": str(runtime_python),
        "runtimeManifest": str(runtime_manifest_path),
        "adapterPath": str(adapter_path),
        "returnCode": completed.returncode,
        "failureClass": failure_class,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "recommendation": recommendation(failure_class),
    }

def recommendation(failure_class: str | None) -> str:
    if failure_class == "WINDOWS_APPLICATION_CONTROL_BLOCKED_TORCH_DLL":
        return "Run GreedRL native in WSL/container or add a WDAC allow rule for the trusted Python/Torch runtime path; lite mode remains PASS_WITH_LIMITS only."
    if failure_class == "GREEDRL_NATIVE_MODULE_MISSING":
        return "Materialize the GreedRL native package into the configured Python 3.8 runtime, then rerun this probe."
    if failure_class == "MODEL_FINGERPRINT_MISMATCH":
        return "Rematerialize the GreedRL model/runtime artifact so manifest fingerprint and local files match."
    if failure_class == "GREEDRL_NATIVE_RUNTIME_TIMEOUT":
        return "Native GreedRL import did not complete within probe budget. Run it in WSL/container or inspect the native Python/Torch runtime outside the Windows-controlled path."
    if failure_class is None:
        return "Native GreedRL runtime self-check passed; rerun full-system E2E without IRX_GREEDRL_RUNTIME_MODE=lite."
    return "Inspect stderr/stdout and rerun with a trusted native GreedRL runtime."


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe GreedRL native runtime readiness and classify blocker.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run_native_probe()
    except Exception as exc:
        report = {
            "schemaVersion": "greedrl-native-runtime-probe/v1",
            "verdict": "BLOCKED",
            "failureClass": classify_failure(str(exc), ""),
            "exception": repr(exc),
            "recommendation": recommendation(classify_failure(str(exc), "")),
        }
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
