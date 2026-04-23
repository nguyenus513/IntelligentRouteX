import hashlib
import json
import math
import os
import time
from pathlib import Path

import yaml
from fastapi import FastAPI

APP_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = APP_DIR.parent / "models" / "model-manifest.yaml"
BOOTSTRAP_ARTIFACT_PATH = APP_DIR / "artifacts" / "tabular-model.json"
WORKER_NAME = "ml-tabular-worker"
ML_CONTRACT_VERSION = "dispatch-v2-ml/v1"
JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1"
MATERIALIZATION_METADATA_NAME = "materialization-metadata.json"
RUNTIME_MANIFEST_SCHEMA_VERSION = "tabular-runtime-manifest/v1"
MATERIALIZATION_METADATA_SCHEMA_VERSION = "tabular-materialization/v1"
REQUIRED_STAGES = ("eta-residual", "pair", "driver-fit", "route-value")

app = FastAPI(title="ml-tabular-worker")


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
    return _env_text("IRX_TABULAR_WORKER_DEVICE", "IRX_ML_WORKER_DEVICE", default="cpu")


def _worker_dtype() -> str:
    return _env_text("IRX_TABULAR_WORKER_DTYPE", "IRX_ML_WORKER_DTYPE", default="fp32")


def _worker_gpu_memory_allocated_mb() -> int:
    return _env_int("IRX_TABULAR_WORKER_GPU_MEMORY_ALLOCATED_MB", "IRX_ML_WORKER_GPU_MEMORY_ALLOCATED_MB", default=0)


def _worker_batch_size() -> int:
    return max(1, _env_int("IRX_TABULAR_WORKER_BATCH_SIZE", "IRX_ML_WORKER_BATCH_SIZE", default=1))


def _worker_compile_mode() -> str:
    return _env_text("IRX_TABULAR_WORKER_COMPILE_MODE", "IRX_ML_WORKER_COMPILE_MODE", default="eager")


def _worker_version_audit(*, model_loaded: bool, warmup_done: bool) -> dict:
    return {
        "device": _worker_device(),
        "dtype": _worker_dtype(),
        "gpuMemoryAllocatedMb": _worker_gpu_memory_allocated_mb(),
        "batchSize": _worker_batch_size(),
        "compileMode": _worker_compile_mode(),
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


def _loaded_model_fingerprint(model_directory: Path) -> str:
    normalized = json.dumps(_normalized_file_manifest(model_directory), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _artifact_digest(artifact_path: Path) -> str:
    data = artifact_path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _materialization_metadata(local_model_root: Path) -> dict | None:
    return _load_json(_materialization_metadata_path(local_model_root))


def _runtime_manifest(artifact_path: Path) -> dict | None:
    return _load_json(artifact_path)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_materialization_metadata(metadata: dict) -> str:
    if metadata.get("schemaVersion") != MATERIALIZATION_METADATA_SCHEMA_VERSION:
        return "materialization-metadata-schema-mismatch"
    required_fields = (
        "materializerVersion",
        "materializationMode",
        "sourceArtifactPath",
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


def _validate_stage_config(stage_name: str, stage_config: object) -> str:
    if not isinstance(stage_config, dict):
        return f"runtime-manifest-stage-config-missing:{stage_name}"
    if not isinstance(stage_config.get("weights"), dict) or not stage_config.get("weights"):
        return f"runtime-manifest-stage-config-missing:{stage_name}"
    for field in ("bias", "outputScale", "uncertaintyBias"):
        value = stage_config.get(field)
        if not isinstance(value, (int, float)):
            return f"runtime-manifest-stage-config-missing:{stage_name}"
    return ""


def _validate_runtime_manifest(runtime_manifest: dict) -> str:
    if runtime_manifest.get("schemaVersion") != RUNTIME_MANIFEST_SCHEMA_VERSION:
        return "runtime-manifest-schema-mismatch"
    if runtime_manifest.get("compatibilityContractVersion") != ML_CONTRACT_VERSION:
        return "ml-contract-incompatible"
    if runtime_manifest.get("minSupportedJavaContractVersion") != JAVA_CONTRACT_VERSION:
        return "java-contract-incompatible"
    if not _has_text(runtime_manifest.get("materializerVersion")):
        return "runtime-manifest-provenance-missing"
    if not _has_text(runtime_manifest.get("sourceArtifactPath")):
        return "runtime-manifest-provenance-missing"
    stages = runtime_manifest.get("stages")
    if not isinstance(stages, dict):
        return "runtime-manifest-stages-missing"
    for stage_name in REQUIRED_STAGES:
        reason = _validate_stage_config(stage_name, stages.get(stage_name))
        if reason:
            return reason
    return ""


def _numeric_payload(payload: dict) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in payload.items()
        if isinstance(value, (int, float))
    }


def _request_payload(payload: dict) -> dict:
    return payload.get("payload", payload)


def _stage_config(endpoint: str, runtime_manifest: dict) -> dict:
    stage_key = endpoint.split("/")[-1]
    return runtime_manifest.get("stages", {}).get(stage_key, {})


def _score_for_endpoint(endpoint: str, payload: dict, runtime_manifest: dict) -> tuple[float, float]:
    stage_config = _stage_config(endpoint, runtime_manifest)
    weights = stage_config.get("weights", {})
    numeric_payload = _numeric_payload(payload)
    weighted_sum = float(stage_config.get("bias", 0.0))
    for key, weight in weights.items():
        weighted_sum += numeric_payload.get(key, 0.0) * float(weight)
    raw_score = math.tanh(weighted_sum)
    score = raw_score * float(stage_config.get("outputScale", 1.0))
    uncertainty = max(0.0, min(1.0, float(stage_config.get("uncertaintyBias", 0.1)) + abs(raw_score) * 0.1))
    return score, uncertainty


def _warmup(manifest_entry: dict, runtime_manifest: dict) -> None:
    warmup = manifest_entry.get("startup_warmup_request", {})
    endpoint = warmup.get("endpoint")
    payload = _request_payload(warmup.get("payload", {}))
    if not endpoint or not payload:
        raise ValueError("warmup-payload-missing")
    _score_for_endpoint(endpoint, payload, runtime_manifest)


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
            return False, "runtime-manifest-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint="",
            )
        metadata = _materialization_metadata(local_model_root)
        if metadata is None:
            return False, "materialization-metadata-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint="",
            )
        metadata_validation = _validate_materialization_metadata(metadata)
        if metadata_validation:
            return False, metadata_validation, manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint="",
            )
        model_directory = _model_directory(artifact_path)
        if not model_directory.exists():
            return False, "local-model-directory-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint="",
            )
        loaded_model_fingerprint = _loaded_model_fingerprint(model_directory)
        if not expected_fingerprint:
            return False, "loaded-model-fingerprint-missing", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint=loaded_model_fingerprint,
            )
        if loaded_model_fingerprint != expected_fingerprint:
            return False, "loaded-model-fingerprint-mismatch", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
                materialization_mode=materialization_mode,
                loaded_model_fingerprint=loaded_model_fingerprint,
            )
        if metadata.get("loadedModelFingerprint") != loaded_model_fingerprint:
            return False, "materialization-metadata-mismatch", manifest_entry, None, _version_payload(
                manifest_entry,
                artifact_path=artifact_path,
                loaded_from_local=False,
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

    if ready_requires_local_load:
        assert metadata is not None
        if metadata.get("materializationMode") != materialization_mode:
            return False, "materialization-mode-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourceArtifactPath") != runtime_manifest.get("sourceArtifactPath"):
            return False, "materialization-source-artifact-mismatch", manifest_entry, runtime_manifest, version_payload
        expected_artifact_path = _canonical_path(manifest_entry.get("local_artifact_path"))
        if (
                expected_artifact_path is None
                or metadata.get("modelArtifactPath") != expected_artifact_path.relative_to(_manifest_path().parent).as_posix()
        ):
            return False, "materialization-artifact-path-mismatch", manifest_entry, runtime_manifest, version_payload

    if manifest_entry.get("artifact_digest") != _artifact_digest(artifact_path):
        return False, "artifact-digest-mismatch", manifest_entry, runtime_manifest, version_payload
    if runtime_manifest.get("modelVersion") != manifest_entry.get("model_version"):
        return False, "model-version-mismatch", manifest_entry, runtime_manifest, version_payload

    try:
        _warmup(manifest_entry, runtime_manifest)
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


def _response(endpoint: str, payload: dict) -> dict:
    started_at = time.perf_counter()
    ready, reason, manifest_entry, runtime_manifest, _version = _readiness()
    if not ready or manifest_entry is None or runtime_manifest is None:
        return {
            "schemaVersion": "score-response/v1",
            "traceId": payload.get("traceId", "unknown"),
            "sourceModel": manifest_entry.get("model_name", "tabular-unavailable") if manifest_entry else "tabular-unavailable",
            "modelVersion": manifest_entry.get("model_version", "unavailable") if manifest_entry else "unavailable",
            "artifactDigest": manifest_entry.get("artifact_digest", "") if manifest_entry else "",
            "latencyMs": int((time.perf_counter() - started_at) * 1000),
            "fallbackUsed": True,
            "payload": {
                "score": 0.0,
                "uncertainty": 1.0,
                "reason": reason,
            },
        }
    try:
        score, uncertainty = _score_for_endpoint(endpoint, _request_payload(payload), runtime_manifest)
    except Exception:
        return {
            "schemaVersion": "score-response/v1",
            "traceId": payload.get("traceId", "unknown"),
            "sourceModel": manifest_entry["model_name"],
            "modelVersion": manifest_entry["model_version"],
            "artifactDigest": manifest_entry["artifact_digest"],
            "latencyMs": int((time.perf_counter() - started_at) * 1000),
            "fallbackUsed": True,
            "payload": {
                "score": 0.0,
                "uncertainty": 1.0,
                "reason": "tabular-inference-failed",
            },
        }
    return {
        "schemaVersion": "score-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry["model_name"],
        "modelVersion": manifest_entry["model_version"],
        "artifactDigest": manifest_entry["artifact_digest"],
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": False,
        "payload": {
            "score": score,
            "uncertainty": uncertainty,
        },
    }


@app.get("/health")
def health():
    return {"schemaVersion": "worker-health/v1", "status": "ok"}


@app.get("/ready")
def ready():
    is_ready, reason, _manifest, _runtime_manifest, _version = _readiness()
    return {"schemaVersion": "worker-ready/v1", "ready": is_ready, "reason": reason}


@app.get("/version")
def version():
    _ready, _reason, manifest_entry, _runtime_manifest, version_payload = _readiness()
    if manifest_entry is None:
        return _version_payload(None)
    return version_payload


@app.post("/score/eta-residual")
def score_eta_residual(payload: dict):
    return _response("/score/eta-residual", payload)


@app.post("/score/pair")
def score_pair(payload: dict):
    return _response("/score/pair", payload)


@app.post("/score/driver-fit")
def score_driver_fit(payload: dict):
    return _response("/score/driver-fit", payload)


@app.post("/score/route-value")
def score_route_value(payload: dict):
    return _response("/score/route-value", payload)
