import hashlib
import itertools
import json
import os
import time
from pathlib import Path

import yaml
from fastapi import FastAPI

APP_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = APP_DIR.parent / "models" / "model-manifest.yaml"
BOOTSTRAP_ARTIFACT_PATH = APP_DIR / "artifacts" / "routefinder-model.json"
WORKER_NAME = "ml-routefinder-worker"
ML_CONTRACT_VERSION = "dispatch-v2-ml/v1"
JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1"
MATERIALIZATION_METADATA_NAME = "materialization-metadata.json"
PROMOTED_ARTIFACT_SCHEMA_VERSION = "routefinder-promoted-artifact/v2"
MATERIALIZATION_METADATA_SCHEMA_VERSION = "routefinder-materialization/v2"

app = FastAPI(title="ml-routefinder-worker")


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
    requested = _env_text("IRX_ROUTEFINDER_WORKER_DEVICE", "IRX_ML_WORKER_DEVICE", default="cpu")
    return "cpu" if requested.lower() in {"auto", "gpu", "cuda", "cuda:0"} else requested


def _worker_dtype() -> str:
    return _env_text("IRX_ROUTEFINDER_WORKER_DTYPE", "IRX_ML_WORKER_DTYPE", default="fp32")


def _worker_gpu_memory_allocated_mb() -> int:
    return _env_int("IRX_ROUTEFINDER_WORKER_GPU_MEMORY_ALLOCATED_MB", "IRX_ML_WORKER_GPU_MEMORY_ALLOCATED_MB", default=0)


def _worker_batch_size() -> int:
    return max(1, _env_int("IRX_ROUTEFINDER_WORKER_BATCH_SIZE", "IRX_ML_WORKER_BATCH_SIZE", default=1))


def _worker_compile_mode() -> str:
    return _env_text("IRX_ROUTEFINDER_WORKER_COMPILE_MODE", "IRX_ML_WORKER_COMPILE_MODE", default="eager")


def _worker_version_audit(*, model_loaded: bool, warmup_done: bool) -> dict:
    requested_device = _env_text("IRX_ROUTEFINDER_WORKER_DEVICE", "IRX_ML_WORKER_DEVICE", default="cpu")
    gpu_requested = requested_device.lower() in {"auto", "gpu", "cuda", "cuda:0"} or requested_device.lower().startswith("cuda")
    return {
        "device": _worker_device(),
        "requestedDevice": requested_device,
        "gpuAcceleration": False,
        "gpuAccelerationReason": "routefinder-json-heuristic-has-no-gpu-backend" if gpu_requested else "cpu-selected",
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


def _artifact_digest(artifact_path: Path) -> str:
    data = artifact_path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_artifact(artifact_path: Path) -> dict | None:
    if not artifact_path.exists():
        return None
    return json.loads(artifact_path.read_text(encoding="utf-8"))


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


def _materialization_metadata(local_model_root: Path) -> dict | None:
    metadata_path = _materialization_metadata_path(local_model_root)
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_materialization_metadata(metadata: dict) -> str:
    if metadata.get("schemaVersion") != MATERIALIZATION_METADATA_SCHEMA_VERSION:
        return "materialization-metadata-schema-mismatch"
    required_fields = (
        "materializerVersion",
        "sourceRepository",
        "sourceRef",
        "sourceCommit",
        "sourceDownloadCommand",
        "sourceTestCommand",
        "sourceCheckpointPath",
        "sourceCheckpointDigest",
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


def _validate_promoted_artifact(artifact: dict) -> str:
    if artifact.get("schemaVersion") != PROMOTED_ARTIFACT_SCHEMA_VERSION:
        return "promoted-artifact-schema-mismatch"
    if artifact.get("compatibilityContractVersion") != ML_CONTRACT_VERSION:
        return "ml-contract-incompatible"
    if artifact.get("minSupportedJavaContractVersion") != JAVA_CONTRACT_VERSION:
        return "java-contract-incompatible"
    required_fields = (
        "sourceRepository",
        "sourceRef",
        "sourceCommit",
        "sourceCheckpointPath",
        "sourceCheckpointDigest",
    )
    for field in required_fields:
        if not _has_text(artifact.get(field)):
            return "promoted-artifact-provenance-missing"
    return ""


def _route_payload(payload: dict) -> dict:
    return payload.get("payload", payload)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _signature(stop_order: list[str]) -> str:
    return ">".join(stop_order)


def _disruption(baseline_stop_order: list[str], stop_order: list[str]) -> float:
    baseline_remainder = baseline_stop_order[1:]
    remainder = stop_order[1:]
    if not baseline_remainder:
        return 0.0
    changed = sum(1 for left, right in zip(baseline_remainder, remainder) if left != right)
    return changed / len(baseline_remainder)


def _route_score(stop_order: list[str], payload: dict, config: dict) -> float:
    hashed = int(hashlib.sha256(_signature(stop_order).encode("utf-8")).hexdigest()[:8], 16)
    lexical_tie_break = (hashed / 0xFFFFFFFF) * float(config.get("lexicalTieBreakScale", 0.01))
    return _clamp(
        float(config.get("baseScore", 0.60))
        + float(payload.get("averagePairSupport", 0.0)) * float(config.get("supportWeight", 0.16))
        + float(payload.get("rerankScore", 0.0)) * float(config.get("rerankWeight", 0.12))
        + float(payload.get("bundleScore", 0.0)) * float(config.get("bundleWeight", 0.10))
        + float(payload.get("anchorScore", 0.0)) * float(config.get("anchorWeight", 0.08))
        - _disruption(payload.get("baselineStopOrder", []), stop_order) * float(config.get("disruptionPenalty", 0.12))
        - (float(config.get("boundaryPenalty", 0.06)) if payload.get("boundaryCross", False) else 0.0)
        + lexical_tie_break
    )


def _route_projection(stop_order: list[str], payload: dict, config: dict) -> tuple[float, float]:
    disruption = _disruption(payload.get("baselineStopOrder", []), stop_order)
    pickup_eta = float(payload.get("projectedPickupEtaMinutes", 0.0)) + disruption * float(config.get("pickupShiftPerSwap", 1.2))
    completion_eta = float(payload.get("projectedCompletionEtaMinutes", 0.0)) + disruption * float(config.get("completionShiftPerSwap", 2.5))
    return pickup_eta, max(pickup_eta, completion_eta)


def _candidate_routes(payload: dict) -> list[list[str]]:
    anchor_order_id = payload.get("anchorOrderId")
    bundle_order_ids = [order_id for order_id in payload.get("bundleOrderIds", []) if order_id != anchor_order_id]
    baseline_stop_order = payload.get("baselineStopOrder", [])
    candidates = []
    if baseline_stop_order:
        candidates.append(list(baseline_stop_order))
    for permutation in itertools.permutations(bundle_order_ids):
        candidate = [anchor_order_id, *permutation]
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _generate_alternatives(payload: dict, artifact: dict) -> list[dict]:
    config = artifact.get("alternatives", {})
    max_routes = max(
        1,
        min(
            int(payload.get("maxAlternatives", 1)),
            int(config.get("maxGeneratedRoutes", 3)),
        ),
    )
    ranked = []
    for stop_order in _candidate_routes(payload):
        pickup_eta, completion_eta = _route_projection(stop_order, payload, config)
        ranked.append(
            {
                "stopOrder": stop_order,
                "projectedPickupEtaMinutes": pickup_eta,
                "projectedCompletionEtaMinutes": completion_eta,
                "routeScore": _route_score(stop_order, payload, config),
                "traceReasons": ["routefinder-alternative", f"signature:{_signature(stop_order)}"],
            }
        )
    ranked.sort(key=lambda route: (-route["routeScore"], route["projectedPickupEtaMinutes"], _signature(route["stopOrder"])))
    return ranked[:max_routes]


def _refine_route(payload: dict, artifact: dict) -> list[dict]:
    config = artifact.get("refine", {})
    alternatives = _generate_alternatives(payload, artifact)
    if not alternatives:
        return []
    refined = dict(alternatives[0])
    refined["projectedPickupEtaMinutes"] = max(
        0.0,
        refined["projectedPickupEtaMinutes"] - float(config.get("pickupImprovementMinutes", 0.6)),
    )
    refined["projectedCompletionEtaMinutes"] = max(
        refined["projectedPickupEtaMinutes"],
        refined["projectedCompletionEtaMinutes"] - float(config.get("completionImprovementMinutes", 1.4)),
    )
    refined["routeScore"] = _clamp(refined["routeScore"] + float(config.get("scoreLift", 0.05)))
    refined["traceReasons"] = ["routefinder-refined", f"signature:{_signature(refined['stopOrder'])}"]
    return [refined]


def _warmup(manifest_entry: dict, artifact: dict) -> None:
    warmup = manifest_entry.get("startup_warmup_request", {})
    payload = _route_payload(warmup.get("payload", {}))
    if not payload:
        raise ValueError("warmup-payload-missing")
    if not _generate_alternatives(payload, artifact):
        raise ValueError("alternatives-warmup-empty")
    if not _refine_route(payload, artifact):
        raise ValueError("refine-warmup-empty")


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

    if ready_requires_local_load:
        local_model_root = _canonical_path(manifest_entry.get("local_model_root"))
        if local_model_root is None:
            return False, "local-model-root-missing", manifest_entry, None, version_payload
        if not local_model_root.exists():
            return False, "local-model-root-missing", manifest_entry, None, version_payload
        if not artifact_path.exists():
            return False, "local-artifact-missing", manifest_entry, None, _version_payload(
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
        artifact = _load_artifact(artifact_path)
    except Exception:
        return False, "artifact-load-failed", manifest_entry, None, version_payload
    if artifact is None:
        return False, "artifact-missing", manifest_entry, None, version_payload
    artifact_validation = _validate_promoted_artifact(artifact)
    if artifact_validation:
        return False, artifact_validation, manifest_entry, artifact, version_payload
    if ready_requires_local_load:
        if metadata.get("sourceRepository") != artifact.get("sourceRepository"):
            return False, "materialization-source-repository-mismatch", manifest_entry, artifact, version_payload
        if metadata.get("sourceRef") != artifact.get("sourceRef"):
            return False, "materialization-source-ref-mismatch", manifest_entry, artifact, version_payload
        if metadata.get("sourceCheckpointPath") != artifact.get("sourceCheckpointPath"):
            return False, "materialization-source-checkpoint-path-mismatch", manifest_entry, artifact, version_payload
        if metadata.get("sourceCheckpointDigest") != artifact.get("sourceCheckpointDigest"):
            return False, "materialization-source-checkpoint-digest-mismatch", manifest_entry, artifact, version_payload
        if metadata.get("modelArtifactPath") != _canonical_path(manifest_entry.get("local_artifact_path")).relative_to(_manifest_path().parent).as_posix():
            return False, "materialization-artifact-path-mismatch", manifest_entry, artifact, version_payload
    if _has_text(manifest_entry.get("source_repository")) and artifact.get("sourceRepository") != manifest_entry.get("source_repository"):
        return False, "source-repository-mismatch", manifest_entry, artifact, version_payload
    if _has_text(manifest_entry.get("source_ref")) and artifact.get("sourceRef") != manifest_entry.get("source_ref"):
        return False, "source-ref-mismatch", manifest_entry, artifact, version_payload
    if _has_text(manifest_entry.get("source_checkpoint_path")) and artifact.get("sourceCheckpointPath") != manifest_entry.get("source_checkpoint_path"):
        return False, "source-checkpoint-path-mismatch", manifest_entry, artifact, version_payload
    if manifest_entry.get("artifact_digest") != _artifact_digest(artifact_path):
        return False, "artifact-digest-mismatch", manifest_entry, artifact, version_payload
    if artifact.get("modelVersion") != manifest_entry.get("model_version"):
        return False, "model-version-mismatch", manifest_entry, artifact, version_payload
    try:
        _warmup(manifest_entry, artifact)
    except Exception:
        return False, "warmup-failed", manifest_entry, artifact, version_payload
    return True, "", manifest_entry, artifact, _version_payload(
        manifest_entry,
        artifact_path=artifact_path,
        loaded_from_local=loaded_from_local,
        materialization_mode=materialization_mode,
        loaded_model_fingerprint=loaded_model_fingerprint,
        model_loaded=True,
        warmup_done=True,
    )


def _response(payload: dict, response_type: str) -> dict:
    started_at = time.perf_counter()
    ready, reason, manifest_entry, artifact, _version = _readiness()
    if not ready or manifest_entry is None or artifact is None:
        return {
            "schemaVersion": "routefinder-response/v1",
            "traceId": payload.get("traceId", "unknown"),
            "sourceModel": manifest_entry.get("model_name", "routefinder-unavailable") if manifest_entry else "routefinder-unavailable",
            "modelVersion": manifest_entry.get("model_version", "unavailable") if manifest_entry else "unavailable",
            "artifactDigest": manifest_entry.get("artifact_digest", "") if manifest_entry else "",
            "latencyMs": int((time.perf_counter() - started_at) * 1000),
            "fallbackUsed": True,
            "payload": {"routes": [], "reason": reason},
        }
    routes = _generate_alternatives(_route_payload(payload), artifact) if response_type == "alternatives" else _refine_route(_route_payload(payload), artifact)
    return {
        "schemaVersion": "routefinder-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry["model_name"],
        "modelVersion": manifest_entry["model_version"],
        "artifactDigest": manifest_entry["artifact_digest"],
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": False,
        "payload": {"routes": routes},
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


@app.post("/route/alternatives")
def route_alternatives(payload: dict):
    return _response(payload, "alternatives")


@app.post("/route/refine")
def route_refine(payload: dict):
    return _response(payload, "refine")
