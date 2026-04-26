import hashlib
import importlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

APP_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = APP_DIR.parent / "models" / "model-manifest.yaml"
BOOTSTRAP_ARTIFACT_PATH = APP_DIR / "artifacts" / "chronos-model.json"
WORKER_NAME = "ml-forecast-worker"
ML_CONTRACT_VERSION = "dispatch-v2-ml/v1"
JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1"
MATERIALIZATION_METADATA_NAME = "materialization-metadata.json"
PROMOTED_RUNTIME_MANIFEST_SCHEMA_VERSION = "chronos-runtime-manifest/v1"
MATERIALIZATION_METADATA_SCHEMA_VERSION = "chronos-materialization/v1"
SNAPSHOT_DIRECTORY_NAME = "snapshot"
CONTEXT_LENGTH = 16
BIN_MINUTES = 5
MIN_PREDICTION_LENGTH = 3
MAX_PREDICTION_LENGTH = 12
QUANTILE_LEVELS = (0.1, 0.5, 0.9)
FIXED_TIMESTAMP = "2026-01-01T00:00:00Z"
RUNTIME_CACHE: dict[str, Any] = {
    "fingerprint": None,
    "snapshot_dir": None,
    "pipeline": None,
    "device": None,
}

app = FastAPI(title="ml-forecast-worker")


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
    return _resolved_worker_device()["device"]


def _worker_dtype() -> str:
    return _env_text("IRX_FORECAST_WORKER_DTYPE", "IRX_ML_WORKER_DTYPE", default="fp32")


def _worker_gpu_memory_allocated_mb() -> int:
    configured = _env_int("IRX_FORECAST_WORKER_GPU_MEMORY_ALLOCATED_MB", "IRX_ML_WORKER_GPU_MEMORY_ALLOCATED_MB", default=0)
    if configured > 0:
        return configured
    try:
        torch_module = importlib.import_module("torch")
        if hasattr(torch_module, "cuda") and torch_module.cuda.is_available():
            return int(torch_module.cuda.memory_allocated() / (1024 * 1024))
    except Exception:
        return 0
    return 0


def _worker_batch_size() -> int:
    return max(1, _env_int("IRX_FORECAST_WORKER_BATCH_SIZE", "IRX_ML_WORKER_BATCH_SIZE", default=1))


def _worker_compile_mode() -> str:
    return _env_text("IRX_FORECAST_WORKER_COMPILE_MODE", "IRX_ML_WORKER_COMPILE_MODE", default="eager")


def _worker_version_audit(*, model_loaded: bool, warmup_done: bool) -> dict:
    device_resolution = _resolved_worker_device()
    return {
        "device": device_resolution["device"],
        "requestedDevice": device_resolution["requestedDevice"],
        "deviceResolvedFrom": device_resolution["source"],
        "gpuAcceleration": device_resolution["gpuAcceleration"],
        "gpuAccelerationReason": device_resolution["reason"],
        "dtype": _worker_dtype(),
        "gpuMemoryAllocatedMb": _worker_gpu_memory_allocated_mb(),
        "batchSize": _worker_batch_size(),
        "compileMode": _worker_compile_mode(),
        "modelLoaded": model_loaded,
        "warmupDone": warmup_done,
    }


def _torch_cuda_available() -> bool:
    try:
        torch_module = importlib.import_module("torch")
        return bool(hasattr(torch_module, "cuda") and torch_module.cuda.is_available())
    except Exception:
        return False


def _requested_worker_device() -> tuple[str, str]:
    for key in ("IRX_FORECAST_WORKER_DEVICE", "IRX_ML_WORKER_DEVICE"):
        value = os.getenv(key, "").strip()
        if value:
            return value, key
    return "cpu", "default"


def _resolved_worker_device() -> dict[str, Any]:
    requested, source = _requested_worker_device()
    normalized = requested.lower()
    if normalized in {"auto", "gpu", "cuda"}:
        requested = "cuda:0"
        normalized = requested
    if normalized.startswith("cuda"):
        if _torch_cuda_available():
            return {
                "device": requested,
                "requestedDevice": requested,
                "source": source,
                "gpuAcceleration": True,
                "reason": "cuda-available",
            }
        if _env_text("IRX_FORECAST_STRICT_DEVICE", "IRX_ML_STRICT_DEVICE", default="").lower() in {"1", "true", "yes"}:
            raise RuntimeError("forecast-cuda-requested-but-unavailable")
        return {
            "device": "cpu",
            "requestedDevice": requested,
            "source": source,
            "gpuAcceleration": False,
            "reason": "cuda-requested-but-unavailable-fallback-cpu",
        }
    return {
        "device": "cpu",
        "requestedDevice": requested,
        "source": source,
        "gpuAcceleration": False,
        "reason": "cpu-selected",
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


def _directory_digest(directory: Path) -> str:
    normalized = json.dumps(_normalized_file_manifest(directory), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _loaded_model_fingerprint(model_directory: Path) -> str:
    return _directory_digest(model_directory)


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
        "sourceModelId",
        "sourceModelRevision",
        "sourcePackageRequirement",
        "sourceDownloadCommand",
        "sourceTestCommand",
        "sourceSnapshotPath",
        "sourceSnapshotDigest",
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
        "sourceModelId",
        "sourceModelRevision",
        "sourcePackageRequirement",
        "sourceSnapshotPath",
        "sourceSnapshotDigest",
    )
    for field in required_fields:
        if not _has_text(runtime_manifest.get(field)):
            return "runtime-manifest-provenance-missing"
    if not isinstance(runtime_manifest.get("adapterCalibration"), dict) or not runtime_manifest.get("adapterCalibration"):
        return "runtime-manifest-calibration-missing"
    return ""


def _stage_calibration(endpoint: str, runtime_manifest: dict) -> dict:
    return runtime_manifest.get("adapterCalibration", {}).get(endpoint.split("/")[-1], {})


def _prediction_length(horizon_minutes: int) -> int:
    if horizon_minutes <= 0:
        return MIN_PREDICTION_LENGTH
    return max(MIN_PREDICTION_LENGTH, min(MAX_PREDICTION_LENGTH, math.ceil(horizon_minutes / BIN_MINUTES)))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _clamp_symmetric(value: float, bound: float = 1.0) -> float:
    return max(-bound, min(bound, value))


def _set_deterministic_seed() -> None:
    try:
        torch_module = importlib.import_module("torch")
        torch_module.manual_seed(0)
        if hasattr(torch_module, "cuda") and torch_module.cuda.is_available():
            torch_module.cuda.manual_seed_all(0)
    except Exception:
        return


def _import_runtime_dependencies():
    chronos_module = importlib.import_module("chronos")
    pandas_module = importlib.import_module("pandas")
    return chronos_module, pandas_module


def _load_pipeline_from_snapshot(snapshot_dir: Path):
    _set_deterministic_seed()
    chronos_module, _pandas = _import_runtime_dependencies()
    device = _resolved_worker_device()["device"]
    return chronos_module.Chronos2Pipeline.from_pretrained(str(snapshot_dir), device_map=device)


def _ensure_loaded_pipeline(runtime_manifest: dict, artifact_path: Path, loaded_model_fingerprint: str):
    snapshot_dir = _model_directory(artifact_path) / runtime_manifest.get("sourceSnapshotPath", SNAPSHOT_DIRECTORY_NAME)
    cached_fingerprint = RUNTIME_CACHE.get("fingerprint")
    cached_snapshot_dir = RUNTIME_CACHE.get("snapshot_dir")
    cached_pipeline = RUNTIME_CACHE.get("pipeline")
    if (
            cached_pipeline is not None
            and cached_fingerprint == loaded_model_fingerprint
            and cached_snapshot_dir == snapshot_dir
            and RUNTIME_CACHE.get("device") == _resolved_worker_device()["device"]
    ):
        return cached_pipeline
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Chronos snapshot directory not found: {snapshot_dir}")
    pipeline = _load_pipeline_from_snapshot(snapshot_dir)
    RUNTIME_CACHE["fingerprint"] = loaded_model_fingerprint
    RUNTIME_CACHE["snapshot_dir"] = snapshot_dir
    RUNTIME_CACHE["pipeline"] = pipeline
    RUNTIME_CACHE["device"] = _resolved_worker_device()["device"]
    return pipeline


def _build_feature_signals(endpoint: str, payload: dict, calibration: dict) -> dict:
    order_count = max(1.0, float(payload.get("orderCount", 0.0)))
    urgent_count = float(payload.get("urgentOrderCount", 0.0))
    driver_count = max(1.0, float(payload.get("driverCount", 1.0)))
    average_route_value = float(payload.get("averageRouteValue", 0.0))
    average_completion_eta = float(payload.get("averageCompletionEtaMinutes", 0.0))
    signals = {
        "order_pressure": order_count / max(driver_count, 1.0),
        "urgency_ratio": urgent_count / order_count,
        "driver_supply": driver_count / max(order_count, 1.0),
        "route_value": average_route_value,
        "completion_eta": average_completion_eta / 30.0,
        "special_signal": 0.0,
    }
    if endpoint == "/forecast/demand-shift":
        signals["special_signal"] = (
                float(payload.get("averageReadySpreadMinutes", 0.0)) / 10.0
                + float(payload.get("averagePickupEtaMinutes", 0.0)) / 20.0
                + float(payload.get("averageBoundaryParticipation", 0.0))
        ) / 3.0
    elif endpoint == "/forecast/zone-burst":
        signals["special_signal"] = (
                float(payload.get("averageBundleScore", 0.0))
                + float(payload.get("averagePairSupport", 0.0))
        ) / 2.0
    else:
        signals["special_signal"] = (
                float(payload.get("averageDriverRerankScore", 0.0))
                + float(payload.get("averageStabilityProxy", 0.0))
        ) / 2.0

    baseline_signal = float(calibration.get("bias", 0.0))
    baseline_signal += signals["order_pressure"] * float(calibration.get("orderWeight", 0.0))
    baseline_signal += signals["urgency_ratio"] * float(calibration.get("urgentWeight", 0.0))
    baseline_signal += signals["route_value"] * float(calibration.get("valueWeight", 0.0))
    baseline_signal += signals["completion_eta"] * float(calibration.get("completionEtaWeight", 0.0))
    baseline_signal += signals["special_signal"] * float(calibration.get("specialWeight", 0.0))
    baseline_signal -= signals["driver_supply"] * float(calibration.get("driverWeight", 0.0))
    signals["baseline_signal"] = _clamp(baseline_signal)
    return signals


def _build_prediction_frames(endpoint: str, payload: dict, runtime_manifest: dict):
    calibration = _stage_calibration(endpoint, runtime_manifest)
    if not calibration:
        raise ValueError("stage-calibration-missing")
    _, pandas_module = _import_runtime_dependencies()
    signals = _build_feature_signals(endpoint, payload, calibration)
    prediction_length = _prediction_length(int(payload.get("horizonMinutes", calibration.get("defaultHorizonMinutes", 30))))
    context_timestamp = pandas_module.date_range(end=FIXED_TIMESTAMP, periods=CONTEXT_LENGTH, freq=f"{BIN_MINUTES}min")
    future_timestamp = pandas_module.date_range(
        start=context_timestamp[-1] + pandas_module.Timedelta(minutes=BIN_MINUTES),
        periods=prediction_length,
        freq=f"{BIN_MINUTES}min",
    )
    base = signals["baseline_signal"]
    direction = float(calibration.get("direction", 1.0))
    trend = float(calibration.get("trendWeight", 0.035)) * direction * (signals["special_signal"] - 0.5)
    seasonality = float(calibration.get("seasonalityWeight", 0.02))
    context_rows = []
    for index, timestamp in enumerate(context_timestamp):
        centered = index - (CONTEXT_LENGTH - 1) / 2.0
        target = _clamp(
            base
            + centered * trend
            + math.sin(index / 2.0) * seasonality
            + (signals["urgency_ratio"] - 0.5) * 0.04,
            0.0,
            1.0,
        )
        context_rows.append(
            {
                "id": endpoint.split("/")[-1],
                "timestamp": timestamp,
                "target": target,
                "order_pressure": signals["order_pressure"],
                "urgency_ratio": signals["urgency_ratio"],
                "driver_supply": signals["driver_supply"],
                "route_value": signals["route_value"],
                "completion_eta": signals["completion_eta"],
                "special_signal": signals["special_signal"],
            }
        )
    future_rows = []
    for index, timestamp in enumerate(future_timestamp, start=1):
        horizon_ratio = index / prediction_length
        future_rows.append(
            {
                "id": endpoint.split("/")[-1],
                "timestamp": timestamp,
                "order_pressure": signals["order_pressure"] + horizon_ratio * float(calibration.get("futureOrderRamp", 0.0)),
                "urgency_ratio": signals["urgency_ratio"] + horizon_ratio * float(calibration.get("futureUrgencyRamp", 0.0)),
                "driver_supply": signals["driver_supply"] + horizon_ratio * float(calibration.get("futureDriverRamp", 0.0)),
                "route_value": signals["route_value"],
                "completion_eta": signals["completion_eta"] + horizon_ratio * float(calibration.get("futureEtaRamp", 0.0)),
                "special_signal": signals["special_signal"],
            }
        )
    return (
        pandas_module.DataFrame(context_rows),
        pandas_module.DataFrame(future_rows),
        signals,
        calibration,
        prediction_length,
    )


def _quantile_series(prediction_frame, quantile: float):
    candidates = (str(quantile), quantile, f"q{int(quantile * 100)}")
    for candidate in candidates:
        if candidate in prediction_frame.columns:
            return prediction_frame[candidate]
    raise KeyError(f"Missing quantile column {quantile}")


def _forecast_payload(endpoint: str, payload: dict, runtime_manifest: dict, pipeline) -> dict:
    context_df, future_df, signals, calibration, prediction_length = _build_prediction_frames(endpoint, payload, runtime_manifest)
    prediction_frame = pipeline.predict_df(
        context_df,
        future_df=future_df,
        prediction_length=prediction_length,
        quantile_levels=list(QUANTILE_LEVELS),
        id_column="id",
        timestamp_column="timestamp",
        target="target",
    )
    q10 = float(_quantile_series(prediction_frame, 0.1).mean())
    q50 = float(_quantile_series(prediction_frame, 0.5).mean())
    q90 = float(_quantile_series(prediction_frame, 0.9).mean())
    base_probability = signals["baseline_signal"]
    probability = _clamp((base_probability * 0.45) + (q50 * 0.55))
    quantile_scale = float(calibration.get("quantileScale", 1.0))
    direction = float(calibration.get("direction", 1.0))
    quantiles = {
        "q10": round(_clamp_symmetric((q10 - base_probability) * quantile_scale * direction * 2.0), 4),
        "q50": round(_clamp_symmetric((q50 - base_probability) * quantile_scale * direction * 2.0), 4),
        "q90": round(_clamp_symmetric((q90 - base_probability) * quantile_scale * direction * 2.0), 4),
    }
    spread = max(0.0, q90 - q10)
    confidence = _clamp(
        float(calibration.get("baseConfidence", 0.55))
        + probability * float(calibration.get("confidenceLift", 0.2))
        - spread * float(calibration.get("spreadPenalty", 0.35))
    )
    return {
        "horizonMinutes": int(payload.get("horizonMinutes", prediction_length * BIN_MINUTES)),
        "shiftProbability": probability if endpoint != "/forecast/zone-burst" else None,
        "burstProbability": probability if endpoint == "/forecast/zone-burst" else None,
        "quantiles": quantiles,
        "confidence": confidence,
        "sourceAgeMs": int(calibration.get("sourceAgeMs", 120000)),
    }


def _warmup(manifest_entry: dict, runtime_manifest: dict, pipeline) -> None:
    warmup = manifest_entry.get("startup_warmup_request", {})
    payload = _request_payload(warmup.get("payload", {}))
    endpoint = warmup.get("endpoint")
    if not payload or not endpoint:
        raise ValueError("warmup-payload-missing")
    response = _forecast_payload(endpoint, payload, runtime_manifest, pipeline)
    if response.get("confidence", 0.0) <= 0.0:
        raise ValueError("warmup-confidence-missing")


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
        if metadata.get("sourceRepository") != runtime_manifest.get("sourceRepository"):
            return False, "materialization-source-repository-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourceRef") != runtime_manifest.get("sourceRef"):
            return False, "materialization-source-ref-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourceModelId") != runtime_manifest.get("sourceModelId"):
            return False, "materialization-source-model-id-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourceModelRevision") != runtime_manifest.get("sourceModelRevision"):
            return False, "materialization-source-model-revision-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourcePackageRequirement") != runtime_manifest.get("sourcePackageRequirement"):
            return False, "materialization-source-package-mismatch", manifest_entry, runtime_manifest, version_payload
        if metadata.get("sourceSnapshotDigest") != runtime_manifest.get("sourceSnapshotDigest"):
            return False, "materialization-source-snapshot-digest-mismatch", manifest_entry, runtime_manifest, version_payload
        expected_artifact_path = _canonical_path(manifest_entry.get("local_artifact_path"))
        if (
                expected_artifact_path is None
                or metadata.get("modelArtifactPath") != expected_artifact_path.relative_to(_manifest_path().parent).as_posix()
        ):
            return False, "materialization-artifact-path-mismatch", manifest_entry, runtime_manifest, version_payload

    source_field_pairs = (
        ("source_repository", "sourceRepository", "source-repository-mismatch"),
        ("source_ref", "sourceRef", "source-ref-mismatch"),
        ("source_model_id", "sourceModelId", "source-model-id-mismatch"),
        ("source_model_revision", "sourceModelRevision", "source-model-revision-mismatch"),
        ("source_package_requirement", "sourcePackageRequirement", "source-package-requirement-mismatch"),
    )
    for manifest_field, runtime_field, reason in source_field_pairs:
        if _has_text(manifest_entry.get(manifest_field)) and runtime_manifest.get(runtime_field) != manifest_entry.get(manifest_field):
            return False, reason, manifest_entry, runtime_manifest, version_payload

    if manifest_entry.get("artifact_digest") != _artifact_digest(artifact_path):
        return False, "artifact-digest-mismatch", manifest_entry, runtime_manifest, version_payload
    if runtime_manifest.get("modelVersion") != manifest_entry.get("model_version"):
        return False, "model-version-mismatch", manifest_entry, runtime_manifest, version_payload

    try:
        pipeline = _ensure_loaded_pipeline(runtime_manifest, artifact_path, loaded_model_fingerprint)
    except Exception:
        return False, "pipeline-load-failed", manifest_entry, runtime_manifest, version_payload
    try:
        _warmup(manifest_entry, runtime_manifest, pipeline)
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
        "schemaVersion": "forecast-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry.get("model_name", "chronos-unavailable") if manifest_entry else "chronos-unavailable",
        "modelVersion": manifest_entry.get("model_version", "unavailable") if manifest_entry else "unavailable",
        "artifactDigest": manifest_entry.get("artifact_digest", "") if manifest_entry else "",
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": True,
        "payload": {
            "horizonMinutes": 0,
            "shiftProbability": 0.0,
            "burstProbability": 0.0,
            "quantiles": {},
            "confidence": 0.0,
            "sourceAgeMs": 0,
            "reason": reason,
        },
    }


def _response(endpoint: str, payload: dict) -> dict:
    started_at = time.perf_counter()
    ready, reason, manifest_entry, runtime_manifest, _version = _readiness()
    if not ready or manifest_entry is None or runtime_manifest is None:
        return _fallback_response(reason, payload, manifest_entry, started_at)
    try:
        pipeline = _ensure_loaded_pipeline(
            runtime_manifest,
            _artifact_path(manifest_entry),
            _version.get("loadedModelFingerprint", ""),
        )
        response_payload = _forecast_payload(endpoint, _request_payload(payload), runtime_manifest, pipeline)
    except Exception:
        return _fallback_response("forecast-inference-failed", payload, manifest_entry, started_at)
    return {
        "schemaVersion": "forecast-response/v1",
        "traceId": payload.get("traceId", "unknown"),
        "sourceModel": manifest_entry["model_name"],
        "modelVersion": manifest_entry["model_version"],
        "artifactDigest": manifest_entry["artifact_digest"],
        "latencyMs": int((time.perf_counter() - started_at) * 1000),
        "fallbackUsed": False,
        "payload": response_payload,
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


@app.post("/forecast/demand-shift")
def forecast_demand_shift(payload: dict):
    return _response("/forecast/demand-shift", payload)


@app.post("/forecast/zone-burst")
def forecast_zone_burst(payload: dict):
    return _response("/forecast/zone-burst", payload)


@app.post("/forecast/post-drop-shift")
def forecast_post_drop_shift(payload: dict):
    return _response("/forecast/post-drop-shift", payload)
