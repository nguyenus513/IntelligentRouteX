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
SPEC = importlib.util.spec_from_file_location("routefinder_worker_app", MODULE_PATH)
routefinder_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(routefinder_app)

MODEL_ARTIFACT = {
    "schemaVersion": "routefinder-promoted-artifact/v2",
    "modelName": "routefinder-local",
    "modelVersion": "2026.04.18-v2",
    "compatibilityContractVersion": "dispatch-v2-ml/v1",
    "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
    "sourceRepository": "https://github.com/ai4co/routefinder.git",
    "sourceRef": "fe0e45b6df118af03c5f42db8b93a351f7629131",
    "sourceCommit": "fe0e45b6df118af03c5f42db8b93a351f7629131",
    "sourceCheckpointPath": "checkpoints/100/rf-transformer.ckpt",
    "sourceCheckpointDigest": "sha256:checkpoint",
    "alternatives": {
        "maxGeneratedRoutes": 3,
        "baseScore": 0.60,
        "supportWeight": 0.16,
        "rerankWeight": 0.12,
        "bundleWeight": 0.10,
        "anchorWeight": 0.08,
        "disruptionPenalty": 0.12,
        "boundaryPenalty": 0.06,
        "pickupShiftPerSwap": 1.2,
        "completionShiftPerSwap": 2.5,
        "lexicalTieBreakScale": 0.01,
    },
    "refine": {
        "pickupImprovementMinutes": 0.6,
        "completionImprovementMinutes": 1.4,
        "scoreLift": 0.05,
    },
}


class RouteFinderWorkerReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_manifest_path = routefinder_app.MANIFEST_PATH

    def tearDown(self) -> None:
        routefinder_app.MANIFEST_PATH = self._original_manifest_path

    def test_missing_local_model_path_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("local-model-root-missing", reason)
            self.assertFalse(version_payload["loadedFromLocal"])

    def test_manifest_path_env_override_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            with patch.dict(os.environ, {"IRX_MODEL_MANIFEST_PATH": str(manifest_path)}):
                self.assertEqual(manifest_path.resolve(), routefinder_app._manifest_path())

    def test_fingerprint_mismatch_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, _artifact_path, _fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:other")
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("loaded-model-fingerprint-mismatch", reason)
            self.assertEqual(str(model_root / "model" / "routefinder-model.json"), version_payload["localArtifactPath"])

    def test_artifact_load_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root = temp_root / "services" / "models" / "materialized" / "routefinder"
            model_dir = model_root / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = model_dir / "routefinder-model.json"
            artifact_path.write_text("{bad-json", encoding="utf-8")
            fingerprint = routefinder_app._loaded_model_fingerprint(model_dir)
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, _version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("artifact-load-failed", reason)

    def test_warmup_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _artifact_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint, warmup_payload="{}")
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, _version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("warmup-failed", reason)

    def test_promoted_artifact_missing_provenance_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, artifact_path, _fingerprint = self._write_materialized_model(temp_root)
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            del artifact["sourceCheckpointDigest"]
            artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
            fingerprint = routefinder_app._loaded_model_fingerprint(model_root / "model")
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, _version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("promoted-artifact-provenance-missing", reason)

    def test_incomplete_materialization_metadata_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, _artifact_path, fingerprint = self._write_materialized_model(temp_root)
            self._write_metadata(temp_root, model_root, fingerprint, complete=False)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            routefinder_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _artifact, _version_payload = routefinder_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("materialization-metadata-provenance-missing", reason)

    def test_valid_local_model_is_ready_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, artifact_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            routefinder_app.MANIFEST_PATH = manifest_path

            with patch.object(socket.socket, "connect", side_effect=AssertionError("network should not be used")):
                ready, reason, _manifest, artifact, version_payload = routefinder_app._readiness()

            self.assertTrue(ready)
            self.assertEqual("", reason)
            self.assertEqual(MODEL_ARTIFACT["modelVersion"], artifact["modelVersion"])
            self.assertTrue(version_payload["loadedFromLocal"])
            self.assertEqual(str(artifact_path), version_payload["localArtifactPath"])
            self.assertEqual("HF_CHECKPOINT_PROMOTION", version_payload["materializationMode"])
            self.assertEqual(fingerprint, version_payload["loadedModelFingerprint"])
            self.assertEqual("cpu", version_payload["device"])
            self.assertEqual("fp32", version_payload["dtype"])
            self.assertEqual(0, version_payload["gpuMemoryAllocatedMb"])
            self.assertEqual(1, version_payload["batchSize"])
            self.assertEqual("eager", version_payload["compileMode"])
            self.assertTrue(version_payload["modelLoaded"])
            self.assertTrue(version_payload["warmupDone"])

    def _write_materialized_model(self, temp_root: Path) -> tuple[Path, Path, str]:
        model_root = temp_root / "services" / "models" / "materialized" / "routefinder"
        model_dir = model_root / "model"
        model_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = model_dir / "routefinder-model.json"
        artifact_path.write_text(json.dumps(MODEL_ARTIFACT, indent=2), encoding="utf-8")
        fingerprint = routefinder_app._loaded_model_fingerprint(model_dir)
        self._write_metadata(temp_root, model_root, fingerprint, complete=True)
        return model_root, artifact_path, fingerprint

    def _write_metadata(self, temp_root: Path, model_root: Path, fingerprint: str, *, complete: bool) -> None:
        model_dir = model_root / "model"
        metadata = {
            "schemaVersion": "routefinder-materialization/v2",
            "materializerVersion": "routefinder-materializer/v1",
            "materializationMode": "HF_CHECKPOINT_PROMOTION",
            "sourceRepository": "https://github.com/ai4co/routefinder.git",
            "sourceRef": "fe0e45b6df118af03c5f42db8b93a351f7629131",
            "sourceCommit": "fe0e45b6df118af03c5f42db8b93a351f7629131",
            "sourceDownloadCommand": "python scripts/download_hf.py --models --no-data",
            "sourceTestCommand": "python test.py --checkpoint checkpoints/100/rf-transformer.ckpt",
            "sourceCheckpointPath": "checkpoints/100/rf-transformer.ckpt",
            "sourceCheckpointDigest": "sha256:checkpoint",
            "materializedAt": "2026-04-18T00:00:00+00:00",
            "modelArtifactPath": (model_root / "model" / "routefinder-model.json").relative_to(
                temp_root / "services" / "models").as_posix(),
            "loadedModelFingerprint": fingerprint,
            "fileManifest": routefinder_app._normalized_file_manifest(model_dir),
        }
        if not complete:
            metadata["sourceCheckpointDigest"] = ""
        (model_root / "materialization-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def _write_manifest(self, temp_root: Path, *, fingerprint: str, warmup_payload: str | None = None) -> Path:
        artifact_path = temp_root / "services" / "models" / "materialized" / "routefinder" / "model" / "routefinder-model.json"
        artifact_bytes = artifact_path.read_bytes() if artifact_path.exists() else json.dumps(MODEL_ARTIFACT, indent=2).encode("utf-8")
        artifact_digest = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
        manifest_path = temp_root / "services" / "models" / "model-manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload_block = warmup_payload if warmup_payload is not None else textwrap.dedent(
            """
            schemaVersion: route-request/v1
            traceId: warmup-routefinder
            payload:
              schemaVersion: routefinder-feature-vector/v1
              traceId: warmup-routefinder
              bundleId: bundle-warmup
              anchorOrderId: order-1
              driverId: driver-1
              baselineSource: HEURISTIC_FAST
              baselineStopOrder:
                - order-1
                - order-2
                - order-3
              bundleOrderIds:
                - order-1
                - order-2
                - order-3
              projectedPickupEtaMinutes: 5.0
              projectedCompletionEtaMinutes: 18.0
              rerankScore: 0.7
              bundleScore: 0.8
              anchorScore: 0.75
              averagePairSupport: 0.65
              boundaryCross: false
              maxAlternatives: 2
            """
        ).rstrip()
        manifest_path.write_text(textwrap.dedent(
            f"""
            schemaVersion: model-manifest/v2
            workers:
              - worker_name: ml-routefinder-worker
                model_name: routefinder-local
                model_version: 2026.04.18-v2
                artifact_digest: {artifact_digest}
                rollback_artifact_digest: sha256:rollback
                runtime_image: local/test
                compatibility_contract_version: dispatch-v2-ml/v1
                min_supported_java_contract_version: dispatch-v2-java/v1
                local_model_root: materialized/routefinder
                local_artifact_path: materialized/routefinder/model/routefinder-model.json
                materialization_mode: HF_CHECKPOINT_PROMOTION
                ready_requires_local_load: true
                offline_boot_supported: true
                loaded_model_fingerprint: {fingerprint}
                source_repository: https://github.com/ai4co/routefinder.git
                source_ref: fe0e45b6df118af03c5f42db8b93a351f7629131
                source_checkpoint_path: checkpoints/100/rf-transformer.ckpt
                source_download_command: python scripts/download_hf.py --models --no-data
                source_test_command: python test.py --checkpoint checkpoints/100/rf-transformer.ckpt
                startup_warmup_request:
                  endpoint: /route/refine
                  payload:
            """
        ).lstrip() + textwrap.indent(payload_block + "\n", " " * 20), encoding="utf-8")
        return manifest_path


if __name__ == "__main__":
    unittest.main()
