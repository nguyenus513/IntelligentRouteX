import importlib.util
import hashlib
import json
import os
import socket
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parent / "app.py"
SPEC = importlib.util.spec_from_file_location("forecast_worker_app", MODULE_PATH)
forecast_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(forecast_app)

RUNTIME_MANIFEST = {
    "schemaVersion": "chronos-runtime-manifest/v1",
    "modelName": "chronos-2",
    "modelVersion": "2026.04.18-v2",
    "compatibilityContractVersion": "dispatch-v2-ml/v1",
    "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
    "sourceRepository": "https://github.com/amazon-science/chronos-forecasting.git",
    "sourceRef": "fd533389c300660f9d8e3a00fcb29e4ca1174745",
    "sourceCommit": "fd533389c300660f9d8e3a00fcb29e4ca1174745",
    "sourceModelId": "amazon/chronos-2",
    "sourceModelRevision": "0f8a440441931157957e2be1a9bce66627d99c76",
    "sourcePackageRequirement": "chronos-forecasting==2.2.2",
    "sourceSnapshotPath": "snapshot",
    "sourceSnapshotDigest": "sha256:snapshot",
    "sourceDownloadCommand": "python -m huggingface_hub snapshot_download --repo-id amazon/chronos-2",
    "sourceTestCommand": "python -c \"from chronos import Chronos2Pipeline\"",
    "contextLength": 16,
    "binMinutes": 5,
    "predictionLengthMin": 3,
    "predictionLengthMax": 12,
    "quantileLevels": [0.1, 0.5, 0.9],
    "adapterCalibration": {
        "zone-burst": {
            "bias": 0.22,
            "orderWeight": 0.11,
            "urgentWeight": 0.10,
            "valueWeight": 0.20,
            "completionEtaWeight": 0.06,
            "specialWeight": 0.14,
            "driverWeight": 0.10,
            "direction": 1.0,
            "trendWeight": 0.04,
            "seasonalityWeight": 0.025,
            "futureOrderRamp": 0.03,
            "futureUrgencyRamp": 0.02,
            "futureDriverRamp": -0.02,
            "futureEtaRamp": 0.005,
            "quantileScale": 1.2,
            "baseConfidence": 0.60,
            "confidenceLift": 0.20,
            "spreadPenalty": 0.32,
            "sourceAgeMs": 90000,
            "defaultHorizonMinutes": 20,
        }
    },
}


class ForecastWorkerReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_manifest_path = forecast_app.MANIFEST_PATH

    def tearDown(self) -> None:
        forecast_app.MANIFEST_PATH = self._original_manifest_path
        forecast_app.RUNTIME_CACHE["fingerprint"] = None
        forecast_app.RUNTIME_CACHE["snapshot_dir"] = None
        forecast_app.RUNTIME_CACHE["pipeline"] = None

    def test_missing_local_model_path_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            forecast_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("local-model-root-missing", reason)
            self.assertFalse(version_payload["loadedFromLocal"])

    def test_manifest_path_env_override_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            with patch.dict(os.environ, {"IRX_MODEL_MANIFEST_PATH": str(manifest_path)}):
                self.assertEqual(manifest_path.resolve(), forecast_app._manifest_path())

    def test_fingerprint_mismatch_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:other")
            forecast_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("loaded-model-fingerprint-mismatch", reason)
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])
            self.assertTrue((model_root / "model" / "snapshot").exists())

    def test_runtime_manifest_load_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root = temp_root / "services" / "models" / "materialized" / "chronos-2"
            model_dir = model_root / "model"
            snapshot_dir = model_dir / "snapshot"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "weights.bin").write_bytes(b"weights")
            runtime_manifest_path = model_dir / "chronos-runtime-manifest.json"
            runtime_manifest_path.write_text("{bad-json", encoding="utf-8")
            fingerprint = forecast_app._loaded_model_fingerprint(model_dir)
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            forecast_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("runtime-manifest-load-failed", reason)

    def test_warmup_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            forecast_app.MANIFEST_PATH = manifest_path

            with patch.object(forecast_app, "_load_pipeline_from_snapshot", return_value=object()), patch.object(
                    forecast_app, "_warmup", side_effect=ValueError("boom")):
                ready, reason, _manifest, _runtime_manifest, _version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("warmup-failed", reason)

    def test_runtime_manifest_missing_provenance_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
            del runtime_manifest["sourceSnapshotDigest"]
            runtime_manifest_path.write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
            fingerprint = forecast_app._loaded_model_fingerprint(model_root / "model")
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            forecast_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("runtime-manifest-provenance-missing", reason)

    def test_incomplete_materialization_metadata_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            self._write_metadata(temp_root, model_root, fingerprint, complete=False)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            forecast_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = forecast_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("materialization-metadata-provenance-missing", reason)

    def test_valid_local_model_is_ready_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            forecast_app.MANIFEST_PATH = manifest_path

            with patch.object(forecast_app, "_load_pipeline_from_snapshot", return_value=object()), patch.object(
                    forecast_app, "_warmup", return_value=None), patch.object(
                    socket.socket, "connect", side_effect=AssertionError("network should not be used")):
                ready, reason, _manifest, runtime_manifest, version_payload = forecast_app._readiness()

            self.assertTrue(ready)
            self.assertEqual("", reason)
            self.assertEqual(RUNTIME_MANIFEST["modelVersion"], runtime_manifest["modelVersion"])
            self.assertTrue(version_payload["loadedFromLocal"])
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])
            self.assertEqual("HF_SNAPSHOT_PROMOTION", version_payload["materializationMode"])
            self.assertEqual(fingerprint, version_payload["loadedModelFingerprint"])
            self.assertEqual("cpu", version_payload["device"])
            self.assertEqual("fp32", version_payload["dtype"])
            self.assertEqual(0, version_payload["gpuMemoryAllocatedMb"])
            self.assertEqual(1, version_payload["batchSize"])
            self.assertEqual("eager", version_payload["compileMode"])
            self.assertTrue(version_payload["modelLoaded"])
            self.assertTrue(version_payload["warmupDone"])

    def _write_materialized_model(self, temp_root: Path) -> tuple[Path, Path, str]:
        model_root = temp_root / "services" / "models" / "materialized" / "chronos-2"
        model_dir = model_root / "model"
        snapshot_dir = model_dir / "snapshot"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "weights.bin").write_bytes(b"weights")
        runtime_manifest_path = model_dir / "chronos-runtime-manifest.json"
        runtime_manifest_path.write_text(json.dumps(RUNTIME_MANIFEST, indent=2), encoding="utf-8")
        fingerprint = forecast_app._loaded_model_fingerprint(model_dir)
        self._write_metadata(temp_root, model_root, fingerprint, complete=True)
        return model_root, runtime_manifest_path, fingerprint

    def _write_metadata(self, temp_root: Path, model_root: Path, fingerprint: str, *, complete: bool) -> None:
        model_dir = model_root / "model"
        metadata = {
            "schemaVersion": "chronos-materialization/v1",
            "materializerVersion": "chronos-materializer/v1",
            "materializationMode": "HF_SNAPSHOT_PROMOTION",
            "sourceRepository": "https://github.com/amazon-science/chronos-forecasting.git",
            "sourceRef": "fd533389c300660f9d8e3a00fcb29e4ca1174745",
            "sourceCommit": "fd533389c300660f9d8e3a00fcb29e4ca1174745",
            "sourceModelId": "amazon/chronos-2",
            "sourceModelRevision": "0f8a440441931157957e2be1a9bce66627d99c76",
            "sourcePackageRequirement": "chronos-forecasting==2.2.2",
            "sourceDownloadCommand": "python -m huggingface_hub snapshot_download --repo-id amazon/chronos-2",
            "sourceTestCommand": "python -c \"from chronos import Chronos2Pipeline\"",
            "sourceSnapshotPath": "snapshot",
            "sourceSnapshotDigest": "sha256:snapshot",
            "materializedAt": "2026-04-18T00:00:00+00:00",
            "modelArtifactPath": (model_root / "model" / "chronos-runtime-manifest.json").relative_to(
                temp_root / "services" / "models").as_posix(),
            "loadedModelFingerprint": fingerprint,
            "fileManifest": forecast_app._normalized_file_manifest(model_dir),
        }
        if not complete:
            metadata["sourceSnapshotDigest"] = ""
        (model_root / "materialization-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def _write_manifest(self, temp_root: Path, *, fingerprint: str) -> Path:
        runtime_manifest_path = temp_root / "services" / "models" / "materialized" / "chronos-2" / "model" / "chronos-runtime-manifest.json"
        runtime_manifest_bytes = runtime_manifest_path.read_bytes() if runtime_manifest_path.exists() else json.dumps(RUNTIME_MANIFEST, indent=2).encode("utf-8")
        artifact_digest = "sha256:" + hashlib.sha256(runtime_manifest_bytes).hexdigest()
        manifest_path = temp_root / "services" / "models" / "model-manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(textwrap.dedent(
            f"""
            schemaVersion: model-manifest/v2
            workers:
              - worker_name: ml-forecast-worker
                model_name: chronos-2
                model_version: 2026.04.18-v2
                artifact_digest: {artifact_digest}
                rollback_artifact_digest: sha256:rollback
                runtime_image: local/test
                compatibility_contract_version: dispatch-v2-ml/v1
                min_supported_java_contract_version: dispatch-v2-java/v1
                local_model_root: materialized/chronos-2
                local_artifact_path: materialized/chronos-2/model/chronos-runtime-manifest.json
                materialization_mode: HF_SNAPSHOT_PROMOTION
                ready_requires_local_load: true
                offline_boot_supported: true
                loaded_model_fingerprint: {fingerprint}
                source_repository: https://github.com/amazon-science/chronos-forecasting.git
                source_ref: fd533389c300660f9d8e3a00fcb29e4ca1174745
                source_model_id: amazon/chronos-2
                source_model_revision: 0f8a440441931157957e2be1a9bce66627d99c76
                source_package_requirement: chronos-forecasting==2.2.2
                source_download_command: python -m huggingface_hub snapshot_download --repo-id amazon/chronos-2
                source_test_command: python -c "from chronos import Chronos2Pipeline"
                startup_warmup_request:
                  endpoint: /forecast/zone-burst
                  payload:
                    schemaVersion: forecast-request/v1
                    traceId: warmup-forecast
                    payload:
                      schemaVersion: zone-burst-feature-vector/v1
                      traceId: warmup-forecast
                      corridorId: corridor-warmup
                      orderCount: 3
                      urgentOrderCount: 1
                      driverCount: 2
                      averageCompletionEtaMinutes: 16.0
                      averageRouteValue: 0.68
                      averageBundleScore: 0.70
                      averagePairSupport: 0.64
                      horizonMinutes: 20
            """
        ).lstrip(), encoding="utf-8")
        return manifest_path


if __name__ == "__main__":
    unittest.main()
