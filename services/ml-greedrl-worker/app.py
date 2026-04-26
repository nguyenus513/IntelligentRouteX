import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

APP_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = APP_DIR.parent / "models" / "model-manifest.yaml"
BOOTSTRAP_ARTIFACT_PATH = APP_DIR / "artifacts" / "greedrl-model.json"
WORKER_NAME = "ml-greedrl-worker"
ML_CONTRACT_VERSION = "dispatch-v2-ml/v1"
JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1"
MATERIALIZATION_METADATA_NAME = "materialization-metadata.json"
PROMOTED_RUNTIME_MANIFEST_SCHEMA_VERSION = "greedrl-runtime-manifest/v1"
MATERIALIZATION_METADATA_SCHEMA_VERSION = "greedrl-materialization/v1"
RUNTIME_CACHE: dict[str, Any] = {"fingerprint": None}

app = FastAPI(title="ml-greedrl-worker")


def _env_text(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return default


def _env_int(*keys: str, default: int = 0) -> int:
    for key in keys:
        value = os.getenv(key, "").strip()
        if not value:
            continue
        try:
            return max(0, int(value))
        except ValueError:
            continue
    return default


def _worker_device() -> str:
    return _env_text("IRX_GREEDRL_WORKER_DEVICE", "IRX_ML_WORKER_DEVICE", default="cpu")


def _worker_dtype() -> str:
    return _env_text("IRX_GREEDRL_WORKER_DTYPE", "IRX_ML_WORKER_DTYPE", default="fp32")


def _worker_gpu_memory_allocated_mb() -> int:
    return _env_int("IRX_GREEDRL_WORKER_GPU_MEMORY_ALLOCATED_MB", "IRX_ML_WORKER_GPU_MEMORY_ALLOCATED_MB", default=0)


def _worker_batch_size() -> int:
    return max(1, _env_int("IRX_GREEDRL_WORKER_BATCH_SIZE", "IRX_ML_WORKER_BATCH_SIZE", default=1))


def _worker_compile_mode() -> str:
    return _env_text("IRX_GREEDRL_WORKER_COMPILE_MODE", "IRX_ML_WORKER_COMPILE_MODE", default="eager")


def _lite_runtime_enabled() -> bool:
    return os.getenv("IRX_GREEDRL_RUNTIME_MODE", "").strip().lower() == "lite"


def _worker_version_audit(*, model_loaded: bool, warmup_done: bool) -> dict:
    return {
        "device": _worker_device(),
        "dtype": _worker_dtype(),
        "gpuMemoryAllocatedMb": _worker_gpu_memory_allocated_mb(),
        "batchSize": _worker_batch_size(),
        "compileMode": _worker_compile_mode(),
        "runtimeMode": "lite" if _lite_runtime_enabled() else "native",
        "modelLoaded": model_loaded,
        "warmupDone": warmup_done,
    }


def _manifest_path() -> Path:
    override = os.getenv("IRX_MODEL_MANIFEST_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return MANIFEST_PATH


def _load_manifest_entry() -> dict | None:
    manifest_path = _manifest_path()
    if not manifest_path.exists():
        return None
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    for worker in manifest.get("workers", []):
        if worker.get("worker_name") == WORKER_NAME:
            return worker
    return None


def _canonical_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (_manifest_path().parent / path).resolve()


def _artifact_path(manifest_entry: dict | None) -> Path:
    local_artifact_path = _canonical_path((manifest_entry or {}).get("local_artifact_path"))
    if local_artifact_path is not None:
        return local_artifact_path
    return BOOTSTRAP_ARTIFACT_PATH


def _model_directory(artifact_path: Path) -> Path:
    return artifact_path if artifact_path.is_dir() else artifact_path.parent


def _materialization_metadata_path(local_model_root: Path) -> Path:
    return local_model_root / MATERIALIZATION_METADATA_NAME


def _normalized_file_manifest(model_directory: Path) -> list[dict]:
    entries: list[dict] = []
    for file_path in sorted(path for path in model_directory.rglob("*") if path.is_file()):
        entries.append(
            {
                "path": file_path.relative_to(model_directory).as_posix(),
                "size": file_path.stat().st_size,
                "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
            }
        )
    return entries


def _directory_digest(model_directory: Path) -> str:
    normalized = json.dumps(_normalized_file_manifest(model_directory), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _loaded_model_fingerprint(model_directory: Path) -> str:
    return _directory_digest(model_directory)


def _artifact_digest(artifact_path: Path) -> str:
    return "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _materialization_metadata(local_model_root: Path) -> dict | None:
    return _load_json(_materialization_metadata_path(local_model_root))


def _runtime_manifest(artifact_path: Path) -> dict | None:
    return _load_json(artifact_path)


def _request_payload(payload: dict) -> dict:
    return payload.get("payload", payload)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_materialization_metadata(metadata: dict) -> str:
    if metadata.get("schemaVersion") != MATERIALIZATION_METADATA_SCHEMA_VERSION:
        return "materialization-metadata-schema-mismatch"
    required_fields = (
        "materializerVersion",
        "materializationMode",
        "sourceRepository",
        "sourceRef",
        "sourcePackageRequirement",
        "sourcePythonRequirement",
        "sourceBuildCommand",
        "sourceTestCommand",
        "runtimePythonExecutable",
        "runtimeModuleRoot",
        "runtimeAdapterPath",
        "materializedAt",
        "modelArtifactPath",
        "loadedModelFingerprint",
    )
    for field in required_fields:
        if not _has_text(metadata.get(field)):
            return "materialization-metadata-provenance-missing"
    if not isinstance(metadata.get("fileManifest"), list) or not metadata.get("fileManifest"):
        return "materialization-metadata-file-manifest-missing"
    return ""


def _validate_runtime_manifest(runtime_manifest: dict) -> str:
    if runtime_manifest.get("schemaVersion") != PROMOTED_RUNTIME_MANIFEST_SCHEMA_VERSION:
        return "runtime-manifest-schema-mismatch"
    if runtime_manifest.get("compatibilityContractVersion") != ML_CONTRACT_VERSION:
        return "ml-contract-incompatible"
    if runtime_manifest.get("minSupportedJavaContractVersion") != JAVA_CONTRACT_VERSION:
        return "java-contract-incompatible"
    required_fields = (
        "sourceRepository",
        "sourceRef",
        "sourcePackageRequirement",
        "sourcePythonRequirement",
        "sourceBuildCommand",
        "runtimePythonExecutable",
        "runtimeModuleRoot",
        "runtimeAdapterPath",
    )
    for field in required_fields:
        if not _has_text(runtime_manifest.get(field)):
            return "runtime-manifest-provenance-missing"
    if not isinstance(runtime_manifest.get("bundleProposal"), dict) or not runtime_manifest.get("bundleProposal"):
        return "runtime-manifest-bundle-config-missing"
    if not isinstance(runtime_manifest.get("sequenceProposal"), dict) or not runtime_manifest.get("sequenceProposal"):
        return "runtime-manifest-sequence-config-missing"
    return ""


def _runtime_python(runtime_manifest: dict, artifact_path: Path) -> Path:
    if _lite_runtime_enabled():
        return Path(sys.executable).resolve()
    override = os.getenv("IRX_GREEDRL_RUNTIME_PYTHON", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    configured = Path(runtime_manifest["runtimePythonExecutable"])
    if configured.is_absolute():
        return configured
    return (_model_directory(artifact_path) / configured).resolve()


def _runtime_root(runtime_python: Path) -> Path:
    if runtime_python.parent.name.lower() in {"scripts", "bin"}:
        return runtime_python.parent.parent
    return runtime_python.parent


def _runtime_module_root(runtime_manifest: dict, artifact_path: Path) -> Path:
    return _model_directory(artifact_path) / runtime_manifest["runtimeModuleRoot"]


def _runtime_adapter_path(runtime_manifest: dict, artifact_path: Path) -> Path:
    return _model_directory(artifact_path) / runtime_manifest["runtimeAdapterPath"]


def _validate_runtime_paths(runtime_manifest: dict, artifact_path: Path) -> str:
    if not _runtime_python(runtime_manifest, artifact_path).exists():
        return "runtime-python-missing"
    if not _runtime_module_root(runtime_manifest, artifact_path).exists():
        return "runtime-module-root-missing"
    if not _runtime_adapter_path(runtime_manifest, artifact_path).exists():
        return "runtime-adapter-missing"
    return ""


def _version_payload(manifest_entry: dict | None,
                     *,
                     artifact_path: Path | None = None,
                     loaded_from_local: bool = False,
                     materialization_mode: str = "",
                     loaded_model_fingerprint: str = "",
                     model_loaded: bool = False,
                     warmup_done: bool = False) -> dict:
    if manifest_entry is None:
        return {
            "schemaVersion": "worker-version/v1",
            "worker": WORKER_NAME,
            "model": "unknown",
            "modelVersion": "unknown",
            "artifactDigest": "",
            "compatibilityContractVersion": ML_CONTRACT_VERSION,
            "minSupportedJavaContractVersion": JAVA_CONTRACT_VERSION,
            "loadedFromLocal": False,
            "localArtifactPath": "",
            "materializationMode": "",
            "loadedModelFingerprint": "",
            **_worker_version_audit(model_loaded=False, warmup_done=False),
        }
    return {
        "schemaVersion": "worker-version/v1",
        "worker": WORKER_NAME,
        "model": manifest_entry["model_name"],
        "modelVersion": manifest_entry["model_version"],
        "artifactDigest": manifest_entry.get("artifact_digest", ""),
        "compatibilityContractVersion": manifest_entry["compatibility_contract_version"],
        "minSupportedJavaContractVersion": manifest_entry["min_supported_java_contract_version"],
        "loadedFromLocal": loaded_from_local,
        "localArtifactPath": str(artifact_path) if artifact_path is not None else "",
        "materializationMode": materialization_mode,
        "loadedModelFingerprint": loaded_model_fingerprint,
        **_worker_version_audit(model_loaded=model_loaded, warmup_done=warmup_done),
    }


def _runtime_env(runtime_manifest: dict, artifact_path: Path) -> dict[str, str]:
    env = dict(**os.environ)
    runtime_python = _runtime_python(runtime_manifest, artifact_path)
    runtime_root = _runtime_root(runtime_python)
    for key in ("VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "PIP_REQUIRE_VIRTUALENV"):
        env.pop(key, None)
    if _lite_runtime_enabled():
        module_root = _runtime_module_root(runtime_manifest, artifact_path)
        env["PYTHONPATH"] = str(module_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env
    env["PYTHONHOME"] = str(runtime_root)
    module_root = _runtime_module_root(runtime_manifest, artifact_path)
    env["PYTHONPATH"] = str(module_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = os.pathsep.join(
        [
            str(runtime_root),
            str(runtime_root / "Scripts"),
            os.environ.get("SystemRoot", r"C:\Windows") + r"\System32",
            os.environ.get("SystemRoot", r"C:\Windows"),
        ]
    )
    return env


def _run_runtime_adapter(runtime_manifest: dict,
                         artifact_path: Path,
                         action: str,
                         payload: dict | None = None,
                         *,
                         timeout_seconds: float = 5.0) -> dict:
    completed = subprocess.run(
        [str(_runtime_python(runtime_manifest, artifact_path)), str(_runtime_adapter_path(runtime_manifest, artifact_path)), "--runtime-manifest", str(artifact_path)],
        input=json.dumps({"action": action, "payload": payload or {}}),
        text=True,
        capture_output=True,
        env=_runtime_env(runtime_manifest, artifact_path),
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(stderr or f"runtime-adapter-failed:{completed.returncode}")
    response = json.loads(completed.stdout)
    if not isinstance(response, dict):
        raise ValueError("runtime-adapter-malformed-response")
    return response


def _warmup(manifest_entry: dict, runtime_manifest: dict, artifact_path: Path) -> None:
    warmup = manifest_entry.get("startup_warmup_request", {})
    payload = _request_payload(warmup.get("payload", {}))
    if not payload:
        raise ValueError("warmup-payload-missing")
    bundle_proposals = _run_runtime_adapter(runtime_manifest, artifact_path, "bundle-propose", payload).get("bundleProposals")
    if not bundle_proposals:
        raise ValueError("bundle-warmup-empty")
    sequence_payload = dict(payload)
    if not sequence_payload.get("orderIds") and bundle_proposals:
        sequence_payload["orderIds"] = bundle_proposals[0].get("orderIds", [])
    if not _run_runtime_adapter(runtime_manifest, artifact_path, "sequence-propose", sequence_payload).get("sequenceProposals"):
        raise ValueError("sequence-warmup-empty")


def _ensure_runtime_ready(manifest_entry: dict, runtime_manifest: dict, artifact_path: Path, loaded_model_fingerprint: str) -> None:
    if RUNTIME_CACHE.get("fingerprint") == loaded_model_fingerprint:
        return
    if not _run_runtime_adapter(runtime_manifest, artifact_path, "self-check").get("ok"):
        raise RuntimeError("runtime-self-check-failed")
    _warmup(manifest_entry, runtime_manifest, artifact_path)
    RUNTIME_CACHE["fingerprint"] = loaded_model_fingerprint


def _readiness() -> tuple[bool, str, dict | None, dict | None, dict]:
    manifest_entry = _load_manifest_entry()
    version_payload = _version_payload(manifest_entry)
    if manifest_entry is None:
        return False, "manifest-worker-missing", None, None, version_payload
    if manifest_entry.get("compatibility_contract_version") != ML_CONTRACT_VERSION:
        return False, "ml-contract-incompatible", manifest_entry, None, version_payload
    if manifest_entry.get("min_supported_java_contract_version") != JAVA_CONTRACT_VERSION:
        return False, "java-contract-incompatible", manifest_entry, None, version_payload

    artifact_path = _artifact_path(manifest_entry)
    materialization_mode = manifest_entry.get("materialization_mode", "")
    expected_fingerprint = manifest_entry.get("loaded_model_fingerprint", "")
    ready_requires_local_load = bool(manifest_entry.get("ready_requires_local_load"))
    loaded_from_local = False
    loaded_model_fingerprint = ""
    metadata = None

    if ready_requires_local_load:
        local_model_root = _canonical_path(manifest_entry.get("local_model_root"))
        if local_model_root is None or not local_model_root.exists():
            return False, "local-model-root-missing", manifest_entry, None, version_payload
        if not artifact_path.exists():
            return False, "local-artifact-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
            )
        metadata = _materialization_metadata(local_model_root)
        if metadata is None:
            return False, "materialization-metadata-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
            )
        metadata_validation = _validate_materialization_metadata(metadata)
        if metadata_validation:
            return False, metadata_validation, manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
            )
        model_directory = _model_directory(artifact_path)
        if not model_directory.exists():
            return False, "local-model-directory-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
            )
        loaded_model_fingerprint = _loaded_model_fingerprint(model_directory)
        if not expected_fingerprint:
            return False, "loaded-model-fingerprint-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint=loaded_model_fingerprint,
            )
        if loaded_model_fingerprint != expected_fingerprint and not _lite_runtime_enabled():
            return False, "loaded-model-fingerprint-mismatch", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint=loaded_model_fingerprint,
            )
        if metadata.get("loadedModelFingerprint") != loaded_model_fingerprint and not _lite_runtime_enabled():
            return False, "materialization-metadata-mismatch", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint=loaded_model_fingerprint,
            )
        loaded_from_local = True

    version_payload = _version_payload(
        manifest_entry,
        artifact_path=artifact_path,
        loaded_from_local=loaded_from_local,
        materialization_mode=materialization_mode,
        loaded_model_fingerprint=loaded_model_fingerprint,
    )
    try:
        runtime_manifest = _runtime_manifest(artifact_path)
    except Exception:
        return False, "runtime-manifest-load-failed", manifest_entry, None, version_payload
    if runtime_manifest is None:
        return False, "runtime-manifest-missing", manifest_entry, None, version_payload
    runtime_manifest_validation = _validate_runtime_manifest(runtime_manifest)
    if runtime_manifest_validation:
        return False, runtime_manifest_validation, manifest_entry, runtime_manifest, version_payload
    runtime_path_validation = _validate_runtime_paths(runtime_manifest, artifact_path)
    if runtime_path_validation:
        return False, runtime_path_validation, manifest_entry, runtime_manifest, version_payload

    if ready_requires_local_load:
        assert metadata is not None
        metadata_field_pairs = (
            ("sourceRepository", "sourceRepository", "materialization-source-repository-mismatch"),
            ("sourceRef", "sourceRef", "materialization-source-ref-mismatch"),
            ("sourcePackageRequirement", "sourcePackageRequirement", "materialization-source-package-mismatch"),
            ("sourcePythonRequirement", "sourcePythonRequirement", "materialization-source-python-mismatch"),
            ("sourceBuildCommand", "sourceBuildCommand", "materialization-source-build-command-mismatch"),
            ("runtimePythonExecutable", "runtimePythonExecutable", "materialization-runtime-python-mismatch"),
            ("runtimeModuleRoot", "runtimeModuleRoot", "materialization-runtime-module-root-mismatch"),
            ("runtimeAdapterPath", "runtimeAdapterPath", "materialization-runtime-adapter-path-mismatch"),
        )
        for metadata_field, runtime_field, reason in metadata_field_pairs:
            if metadata.get(metadata_field) != runtime_manifest.get(runtime_field):
                return False, reason, manifest_entry, runtime_manifest, version_payload
        expected_artifact_path = _canonical_path(manifest_entry.get("local_artifact_path"))
        if expected_artifact_path is None or metadata.get("modelArtifactPath") != expected_artifact_path.relative_to(_manifest_path().parent).as_posix():
            return False, "materialization-artifact-path-mismatch", manifest_entry, runtime_manifest, version_payload

    manifest_field_pairs = (
        ("source_repository", "sourceRepository", "source-repository-mismatch"),
        ("source_ref", "sourceRef", "source-ref-mismatch"),
        ("source_package_requirement", "sourcePackageRequirement", "source-package-requirement-mismatch"),
        ("source_python_requirement", "sourcePythonRequirement", "source-python-requirement-mismatch"),
        ("source_build_command", "sourceBuildCommand", "source-build-command-mismatch"),
    )
    for manifest_field, runtime_field, reason in manifest_field_pairs:
        if _has_text(manifest_entry.get(manifest_field)) and runtime_manifest.get(runtime_field) != manifest_entry.get(manifest_field):
            return False, reason, manifest_entry, runtime_manifest, version_payload
    if manifest_entry.get("artifact_digest") != _artifact_digest(artifact_path):
        return False, "artifact-digest-mismatch", manifest_entry, runtime_manifest, version_payload
    if runtime_manifest.get("modelVersion") != manifest_entry.get("model_version"):
        return False, "model-version-mismatch", manifest_entry, runtime_manifest, version_payload
    try:
        _ensure_runtime_ready(manifest_entry, runtime_manifest, artifact_path, loaded_model_fingerprint)
    except Exception:
        return False, "warmup-failed", manifest_entry, runtime_manifest, version_payload
    return True, "", manifest_entry, runtime_manifest, _version_payload(
        manifest_entry,
        artifact_path=artifact_path,
        loaded_from_local=loaded_from_local,
        materialization_mode=materialization_mode,
        loaded_model_fingerprint=loaded_model_fingerprint,
        model_loaded=True,
        warmup_done=True,
    )


def _fallback_response(reason: str, payload: dict, manifest_entry: dict | None, started_at: float) -> dict:
    return {
        "schemaVersion": "greedrl-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry.get("model_name", "greedrl-unavailable") if manifest_entry else "greedrl-unavailable",
        "modelVersion": manifest_entry.get("model_version", "unavailable") if manifest_entry else "unavailable",
        "artifactDigest": manifest_entry.get("artifact_digest", "") if manifest_entry else "",
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": True,
        "payload": {"bundleProposals": [], "sequenceProposals": [], "reason": reason},
    }


def _response(payload: dict, action: str) -> dict:
    started_at = time.perf_counter()
    ready, reason, manifest_entry, runtime_manifest, version_payload = _readiness()
    if not ready or manifest_entry is None or runtime_manifest is None:
        return _fallback_response(reason, payload, manifest_entry, started_at)
    try:
        runtime_response = _run_runtime_adapter(runtime_manifest, _artifact_path(manifest_entry), action, _request_payload(payload))
    except Exception:
        return _fallback_response("greedrl-inference-failed", payload, manifest_entry, started_at)
    return {
        "schemaVersion": "greedrl-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry["model_name"],
        "modelVersion": manifest_entry["model_version"],
        "artifactDigest": manifest_entry["artifact_digest"],
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": False,
        "payload": {
            "bundleProposals": runtime_response.get("bundleProposals", []),
            "sequenceProposals": runtime_response.get("sequenceProposals", []),
        },
    }


@app.get("/health")
def health():
    return {"schemaVersion": "worker-health/v1", "status": "ok"}


@app.get("/ready")
def ready():
    is_ready, reason, _manifest, _artifact, _version = _readiness()
    return {"schemaVersion": "worker-ready/v1", "ready": is_ready, "reason": reason}


@app.get("/version")
def version():
    _ready, _reason, manifest_entry, _artifact, version_payload = _readiness()
    if manifest_entry is None:
        return _version_payload(None)
    return version_payload


@app.post("/bundle/propose")
def bundle_propose(payload: dict):
    return _response(payload, "bundle-propose")


@app.post("/sequence/propose")
def sequence_propose(payload: dict):
    return _response(payload, "sequence-propose")
