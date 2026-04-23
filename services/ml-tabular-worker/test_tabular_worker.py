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
SPEC = importlib.util.spec_from_file_location("tabular_worker_app", MODULE_PATH)
tabular_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(tabular_app)

RUNTIME_MANIFEST = {
    "schemaVersion": "tabular-runtime-manifest/v1",
    "modelName": "tabular-linear",
    "modelVersion": "2026.04.17-v1",
    "compatibilityContractVersion": "dispatch-v2-ml/v1",
    "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
    "materializerVersion": "tabular-materializer/v1",
    "sourceArtifactPath": "ml-tabular-worker/artifacts/tabular-model.json",
    "stages": {
        "eta-residual": {
            "bias": -0.04,
            "outputScale": 2.0,
            "uncertaintyBias": 0.12,
            "weights": {
                "baselineMinutes": 0.08,
                "trafficMultiplier": 0.30,
            },
        },
        "pair": {
            "bias": 0.01,
            "outputScale": 0.08,
            "uncertaintyBias": 0.10,
            "weights": {
                "pickupDistanceKm": -0.18,
                "dropDistanceKm": -0.03,
            },
        },
        "driver-fit": {
            "bias": 0.03,
            "outputScale": 0.10,
            "uncertaintyBias": 0.10,
            "weights": {
                "pickupEtaMinutes": -0.05,
                "bundleScore": 0.18,
            },
        },
        "route-value": {
            "bias": 0.02,
            "outputScale": 0.09,
            "uncertaintyBias": 0.11,
            "weights": {
                "projectedPickupEtaMinutes": -0.03,
                "deterministicRouteValue": 0.25,
            },
        },
    },
}


class TabularWorkerReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_manifest_path = tabular_app.MANIFEST_PATH

    def tearDown(self) -> None:
        tabular_app.MANIFEST_PATH = self._original_manifest_path

    def test_missing_local_model_path_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            tabular_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = tabular_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("local-model-root-missing", reason)
            self.assertFalse(version_payload["loadedFromLocal"])

    def test_manifest_path_env_override_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            with patch.dict(os.environ, {"IRX_MODEL_MANIFEST_PATH": str(manifest_path)}):
                self.assertEqual(manifest_path.resolve(), tabular_app._manifest_path())

    def test_fingerprint_mismatch_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:other")
            tabular_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = tabular_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("loaded-model-fingerprint-mismatch", reason)
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])

    def test_runtime_manifest_load_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root = temp_root / "services" / "models" / "materialized" / "tabular"
            model_dir = model_root / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            runtime_manifest_path = model_dir / "tabular-runtime-manifest.json"
            runtime_manifest_path.write_text("{bad-json", encoding="utf-8")
            fingerprint = tabular_app._loaded_model_fingerprint(model_dir)
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            tabular_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = tabular_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("runtime-manifest-load-failed", reason)

    def test_warmup_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint, warmup_payload="{}")
            tabular_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = tabular_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("warmup-failed", reason)

    def test_incomplete_materialization_metadata_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            self._write_metadata(temp_root, model_root, fingerprint, complete=False)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            tabular_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = tabular_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("materialization-metadata-provenance-missing", reason)

    def test_valid_local_model_is_ready_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            tabular_app.MANIFEST_PATH = manifest_path

            with patch.object(socket.socket, "connect", side_effect=AssertionError("network should not be used")):
                ready, reason, _manifest, runtime_manifest, version_payload = tabular_app._readiness()

            self.assertTrue(ready)
            self.assertEqual("", reason)
            self.assertEqual(RUNTIME_MANIFEST["modelVersion"], runtime_manifest["modelVersion"])
            self.assertTrue(version_payload["loadedFromLocal"])
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])
            self.assertEqual("LOCAL_FILE_PROMOTION", version_payload["materializationMode"])
            self.assertEqual(fingerprint, version_payload["loadedModelFingerprint"])
            self.assertEqual("cpu", version_payload["device"])
            self.assertEqual("fp32", version_payload["dtype"])
            self.assertEqual(0, version_payload["gpuMemoryAllocatedMb"])
            self.assertEqual(1, version_payload["batchSize"])
            self.assertEqual("eager", version_payload["compileMode"])
            self.assertTrue(version_payload["modelLoaded"])
            self.assertTrue(version_payload["warmupDone"])

    def test_missing_required_stage_configs_leave_worker_not_ready(self) -> None:
        expected = {
            "eta-residual": "runtime-manifest-stage-config-missing:eta-residual",
            "pair": "runtime-manifest-stage-config-missing:pair",
            "driver-fit": "runtime-manifest-stage-config-missing:driver-fit",
            "route-value": "runtime-manifest-stage-config-missing:route-value",
        }
        for stage_name, reason_expected in expected.items():
            with self.subTest(stage_name=stage_name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_root = Path(temp_dir)
                    model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
                    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
                    del runtime_manifest["stages"][stage_name]
                    runtime_manifest_path.write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
                    fingerprint = tabular_app._loaded_model_fingerprint(model_root / "model")
                    self._write_metadata(temp_root, model_root, fingerprint, complete=True)
                    manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
                    tabular_app.MANIFEST_PATH = manifest_path

                    ready, reason, _manifest, _runtime_manifest, _version_payload = tabular_app._readiness()

                    self.assertFalse(ready)
                    self.assertEqual(reason_expected, reason)

    def _write_materialized_model(self, temp_root: Path) -> tuple[Path, Path, str]:
        model_root = temp_root / "services" / "models" / "materialized" / "tabular"
        model_dir = model_root / "model"
        model_dir.mkdir(parents=True, exist_ok=True)
        runtime_manifest_path = model_dir / "tabular-runtime-manifest.json"
        runtime_manifest_path.write_text(json.dumps(RUNTIME_MANIFEST, indent=2), encoding="utf-8")
        fingerprint = tabular_app._loaded_model_fingerprint(model_dir)
        self._write_metadata(temp_root, model_root, fingerprint, complete=True)
        return model_root, runtime_manifest_path, fingerprint

    def _write_metadata(self, temp_root: Path, model_root: Path, fingerprint: str, *, complete: bool) -> None:
        model_dir = model_root / "model"
        metadata = {
            "schemaVersion": "tabular-materialization/v1",
            "materializerVersion": "tabular-materializer/v1",
            "materializationMode": "LOCAL_FILE_PROMOTION",
            "sourceArtifactPath": "ml-tabular-worker/artifacts/tabular-model.json",
            "materializedAt": "2026-04-18T00:00:00+00:00",
            "modelArtifactPath": (model_root / "model" / "tabular-runtime-manifest.json").relative_to(
                temp_root / "services" / "models").as_posix(),
            "loadedModelFingerprint": fingerprint,
            "fileManifest": tabular_app._normalized_file_manifest(model_dir),
        }
        if not complete:
            metadata["sourceArtifactPath"] = ""
        (model_root / "materialization-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def _write_manifest(self, temp_root: Path, *, fingerprint: str, warmup_payload: str | None = None) -> Path:
        runtime_manifest_path = temp_root / "services" / "models" / "materialized" / "tabular" / "model" / "tabular-runtime-manifest.json"
        runtime_manifest_bytes = runtime_manifest_path.read_bytes() if runtime_manifest_path.exists() else json.dumps(RUNTIME_MANIFEST, indent=2).encode("utf-8")
        artifact_digest = "sha256:" + hashlib.sha256(runtime_manifest_bytes).hexdigest()
        manifest_path = temp_root / "services" / "models" / "model-manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload_block = warmup_payload if warmup_payload is not None else textwrap.dedent(
            """
            schemaVersion: score-request/v1
            traceId: warmup-tabular
            payload:
              baselineMinutes: 5.0
              trafficMultiplier: 1.0
              weatherMultiplier: 1.0
              distanceKm: 2.0
              hourOfDay: 12
            """
        ).rstrip()
        manifest_path.write_text(textwrap.dedent(
            f"""
            schemaVersion: model-manifest/v2
            workers:
              - worker_name: ml-tabular-worker
                model_name: tabular-linear
                model_version: 2026.04.17-v1
                artifact_digest: {artifact_digest}
                rollback_artifact_digest: sha256:rollback
                runtime_image: local/test
                compatibility_contract_version: dispatch-v2-ml/v1
                min_supported_java_contract_version: dispatch-v2-java/v1
                local_model_root: materialized/tabular
                local_artifact_path: materialized/tabular/model/tabular-runtime-manifest.json
                materialization_mode: LOCAL_FILE_PROMOTION
                ready_requires_local_load: true
                offline_boot_supported: true
                loaded_model_fingerprint: {fingerprint}
                startup_warmup_request:
                  endpoint: /score/eta-residual
                  payload:
            """
        ).lstrip() + textwrap.indent(payload_block + "\n", " " * 20), encoding="utf-8")
        return manifest_path


if __name__ == "__main__":
    unittest.main()
