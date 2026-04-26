import importlib.util
import hashlib
import json
import os
import socket
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parent / "app.py"
SPEC = importlib.util.spec_from_file_location("greedrl_worker_app", MODULE_PATH)
greedrl_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(greedrl_app)

RUNTIME_MANIFEST = {
    "schemaVersion": "greedrl-runtime-manifest/v1",
    "modelName": "greedrl-local",
    "modelVersion": "2026.04.18-v2",
    "compatibilityContractVersion": "dispatch-v2-ml/v1",
    "minSupportedJavaContractVersion": "dispatch-v2-java/v1",
    "sourceRepository": "https://huggingface.co/Cainiao-AI/GreedRL",
    "sourceRef": "2d5d3bde195dbb5f602908fe42170ffd3ee25c75",
    "sourceCommit": "2d5d3bde195dbb5f602908fe42170ffd3ee25c75",
    "sourcePackageRequirement": "greedrl-community-edition",
    "sourcePythonRequirement": "==3.8.*",
    "sourceBuildCommand": "python setup.py build",
    "sourceTestCommand": "python -c \"import greedrl; import greedrl_c\"",
    "runtimePythonExecutable": "",
    "runtimeModuleRoot": "runtime/build-lib",
    "runtimeAdapterPath": "runtime/greedrl_runtime_adapter.py",
    "bundleProposal": {
        "maxBundleSize": 4,
        "maxGeneratedProposals": 3,
        "perOrderBonus": 0.08,
        "boundaryBonus": 0.12,
        "lexicalTieBreakScale": 0.01,
    },
    "sequenceProposal": {
        "maxGeneratedSequences": 2,
        "baseScore": 0.73,
        "decayPerAlternative": 0.05,
    },
}


class GreedRlWorkerReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_manifest_path = greedrl_app.MANIFEST_PATH

    def tearDown(self) -> None:
        greedrl_app.MANIFEST_PATH = self._original_manifest_path
        greedrl_app.RUNTIME_CACHE["fingerprint"] = None
        greedrl_app.RUNTIME_CACHE.pop("pendingFingerprint", None)
        greedrl_app.RUNTIME_DEVICE_AUDIT.clear()
        greedrl_app._stop_persistent_runtime_adapter()

    def test_missing_local_model_path_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            greedrl_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("local-model-root-missing", reason)
            self.assertFalse(version_payload["loadedFromLocal"])

    def test_manifest_path_env_override_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:expected")
            with patch.dict(os.environ, {"IRX_MODEL_MANIFEST_PATH": str(manifest_path)}):
                self.assertEqual(manifest_path.resolve(), greedrl_app._manifest_path())

    def test_runtime_python_env_override_unblocks_bundle_local_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            bundle_python = temp_root / "bundle" / "runtimes" / "py-greedrl" / "python.exe"
            bundle_python.parent.mkdir(parents=True, exist_ok=True)
            bundle_python.write_text("", encoding="utf-8")
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            def fake_adapter(runtime_manifest, artifact_path, _fingerprint, action, payload=None):
                self.assertEqual(bundle_python.resolve(), greedrl_app._runtime_python(runtime_manifest, artifact_path))
                if action == "self-check":
                    return {"ok": True}
                if action == "bundle-propose":
                    return {"bundleProposals": [{"family": "COMPACT_CLIQUE"}], "sequenceProposals": []}
                return {"bundleProposals": [], "sequenceProposals": [{"stopOrder": ["order-1", "order-2"]}]}

            with patch.dict(os.environ, {"IRX_GREEDRL_RUNTIME_PYTHON": str(bundle_python)}), patch.object(
                    greedrl_app, "_run_model_runtime_adapter", side_effect=fake_adapter):
                ready, reason, _manifest, _runtime_manifest, _version_payload = greedrl_app._readiness()

            self.assertTrue(ready)
            self.assertEqual("", reason)

    def test_runtime_env_sets_pythonhome_from_overridden_bundle_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
            bundle_python = temp_root / "bundle" / "runtimes" / "py-greedrl-model" / "python.exe"
            bundle_python.parent.mkdir(parents=True, exist_ok=True)
            bundle_python.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {"IRX_GREEDRL_RUNTIME_PYTHON": str(bundle_python), "PYTHONHOME": "host-runtime"}):
                env = greedrl_app._runtime_env(runtime_manifest, runtime_manifest_path)

            self.assertEqual(str(bundle_python.parent), env["PYTHONHOME"])
            self.assertIn(str(bundle_python.parent), env["PATH"])
            self.assertEqual(
                str((runtime_manifest_path.parent / "runtime" / "build-lib").resolve()),
                env["PYTHONPATH"],
            )

    def test_runtime_device_audit_detects_cuda_from_runtime_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))

            class Completed:
                returncode = 0
                stdout = '{"cudaAvailable": true}'
                stderr = ""

            with patch.dict(os.environ, {"IRX_GREEDRL_WORKER_DEVICE": "cuda:0"}), patch.object(
                greedrl_app.subprocess, "run", return_value=Completed()
            ):
                audit = greedrl_app._runtime_device_audit(runtime_manifest, runtime_manifest_path)

        self.assertEqual("cuda:0", audit["device"])
        self.assertEqual("cuda:0", audit["requestedDevice"])
        self.assertTrue(audit["gpuAcceleration"])
        self.assertEqual("cuda-available", audit["gpuAccelerationReason"])

    def test_fingerprint_mismatch_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint="sha256:other")
            greedrl_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("loaded-model-fingerprint-mismatch", reason)
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])

    def test_runtime_manifest_load_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root = temp_root / "services" / "models" / "materialized" / "greedrl"
            model_dir = model_root / "model"
            runtime_dir = model_dir / "runtime" / "build-lib"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "runtime" / "greedrl_runtime_adapter.py").write_text("print('noop')", encoding="utf-8")
            runtime_manifest_path = model_dir / "greedrl-runtime-manifest.json"
            runtime_manifest_path.write_text("{bad-json", encoding="utf-8")
            fingerprint = greedrl_app._loaded_model_fingerprint(model_dir)
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("runtime-manifest-load-failed", reason)

    def test_warmup_failure_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            with patch.object(greedrl_app, "_run_runtime_adapter", side_effect=RuntimeError("boom")):
                ready, reason, _manifest, _runtime_manifest, _version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertTrue(reason.startswith("warmup-failed"), reason)

    def test_runtime_manifest_missing_provenance_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, runtime_manifest_path, _fingerprint = self._write_materialized_model(temp_root)
            runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
            del runtime_manifest["runtimeAdapterPath"]
            runtime_manifest_path.write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
            fingerprint = greedrl_app._loaded_model_fingerprint(model_root / "model")
            self._write_metadata(temp_root, model_root, fingerprint, complete=True)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("runtime-manifest-provenance-missing", reason)

    def test_incomplete_materialization_metadata_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            self._write_metadata(temp_root, model_root, fingerprint, complete=False)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            ready, reason, _manifest, _runtime_manifest, _version_payload = greedrl_app._readiness()

            self.assertFalse(ready)
            self.assertEqual("materialization-metadata-provenance-missing", reason)

    def test_valid_local_model_is_ready_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path

            def fake_adapter(runtime_manifest, artifact_path, _fingerprint, action, payload=None):
                if action == "self-check":
                    return {
                        "ok": True,
                        "device": "cuda:0",
                        "requestedDevice": "cuda:0",
                        "gpuAcceleration": True,
                        "gpuAccelerationReason": "cuda-available",
                    }
                if action == "bundle-propose":
                    return {"bundleProposals": [{"family": "COMPACT_CLIQUE"}], "sequenceProposals": []}
                return {"bundleProposals": [], "sequenceProposals": [{"stopOrder": ["order-1", "order-2"]}]}

            with patch.object(greedrl_app, "_run_model_runtime_adapter", side_effect=fake_adapter), patch.object(
                socket.socket, "connect", side_effect=AssertionError("network should not be used")
            ):
                ready, reason, _manifest, runtime_manifest, version_payload = greedrl_app._readiness()

            self.assertTrue(ready)
            self.assertEqual("", reason)
            self.assertEqual(RUNTIME_MANIFEST["modelVersion"], runtime_manifest["modelVersion"])
            self.assertTrue(version_payload["loadedFromLocal"])
            self.assertEqual(str(runtime_manifest_path), version_payload["localArtifactPath"])
            self.assertEqual("LOCAL_PACKAGE_PROMOTION", version_payload["materializationMode"])
            self.assertEqual(fingerprint, version_payload["loadedModelFingerprint"])
            self.assertEqual("cuda:0", version_payload["device"])
            self.assertEqual("cuda:0", version_payload["requestedDevice"])
            self.assertTrue(version_payload["gpuAcceleration"])
            self.assertEqual("cuda-available", version_payload["gpuAccelerationReason"])
            self.assertEqual("fp32", version_payload["dtype"])
            self.assertEqual(0, version_payload["gpuMemoryAllocatedMb"])
            self.assertEqual(1, version_payload["batchSize"])
            self.assertEqual("eager", version_payload["compileMode"])
            self.assertTrue(version_payload["modelLoaded"])
            self.assertTrue(version_payload["warmupDone"])

    def test_response_uses_model_runtime_adapter_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            _model_root, _runtime_manifest_path, fingerprint = self._write_materialized_model(temp_root)
            manifest_path = self._write_manifest(temp_root, fingerprint=fingerprint)
            greedrl_app.MANIFEST_PATH = manifest_path
            actions: list[str] = []

            def fake_adapter(_runtime_manifest, _artifact_path, _fingerprint, action, payload=None):
                actions.append(action)
                if action == "self-check":
                    return {"ok": True, "device": "cpu", "requestedDevice": "cpu", "gpuAcceleration": False}
                if action == "bundle-propose":
                    return {"bundleProposals": [{"family": "COMPACT_CLIQUE", "orderIds": ["order-1"]}], "sequenceProposals": []}
                return {"bundleProposals": [], "sequenceProposals": [{"stopOrder": ["order-1", "order-2"]}]}

            payload = {
                "schemaVersion": "greedrl-request/v1",
                "traceId": "test-response",
                "payload": {
                    "workingOrderIds": ["order-1", "order-2"],
                    "prioritizedOrderIds": ["order-1"],
                    "supportScoreByOrder": {"order-1": 0.8, "order-2": 0.7},
                    "bundleMaxSize": 2,
                    "maxProposals": 1,
                },
            }

            with patch.object(greedrl_app, "_run_model_runtime_adapter", side_effect=fake_adapter), patch.object(
                greedrl_app, "_run_runtime_adapter", side_effect=AssertionError("subprocess adapter should not be used")
            ):
                response = greedrl_app._response(payload, "bundle-propose")

        self.assertFalse(response["fallbackUsed"])
        self.assertEqual(["self-check", "bundle-propose", "sequence-propose", "bundle-propose"], actions)

    def _write_materialized_model(self, temp_root: Path) -> tuple[Path, Path, str]:
        model_root = temp_root / "services" / "models" / "materialized" / "greedrl"
        model_dir = model_root / "model"
        runtime_dir = model_dir / "runtime" / "build-lib"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "greedrl.py").write_text("x = 1\n", encoding="utf-8")
        (runtime_dir / "greedrl_c.py").write_text("x = 1\n", encoding="utf-8")
        adapter_path = model_dir / "runtime" / "greedrl_runtime_adapter.py"
        adapter_path.write_text("print('{\"ok\": true}')", encoding="utf-8")
        runtime_manifest_path = model_dir / "greedrl-runtime-manifest.json"
        runtime_manifest = dict(RUNTIME_MANIFEST)
        runtime_python_path = temp_root / "python38.exe"
        runtime_python_path.write_text("", encoding="utf-8")
        runtime_manifest["runtimePythonExecutable"] = str(runtime_python_path)
        runtime_manifest_path.write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
        fingerprint = greedrl_app._loaded_model_fingerprint(model_dir)
        self._write_metadata(temp_root, model_root, fingerprint, complete=True, runtime_python_executable=runtime_manifest["runtimePythonExecutable"])
        return model_root, runtime_manifest_path, fingerprint

    def _write_metadata(self, temp_root: Path, model_root: Path, fingerprint: str, *, complete: bool, runtime_python_executable: str | None = None) -> None:
        model_dir = model_root / "model"
        metadata = {
            "schemaVersion": "greedrl-materialization/v1",
            "materializerVersion": "greedrl-materializer/v1",
            "materializationMode": "LOCAL_PACKAGE_PROMOTION",
            "sourceRepository": "https://huggingface.co/Cainiao-AI/GreedRL",
            "sourceRef": "2d5d3bde195dbb5f602908fe42170ffd3ee25c75",
            "sourceCommit": "2d5d3bde195dbb5f602908fe42170ffd3ee25c75",
            "sourcePackageRequirement": "greedrl-community-edition",
            "sourcePythonRequirement": "==3.8.*",
            "sourceBuildCommand": "python setup.py build",
            "sourceTestCommand": "python -c \"import greedrl; import greedrl_c\"",
            "runtimePythonExecutable": runtime_python_executable or str(Path(sys.executable).resolve()),
            "runtimeModuleRoot": "runtime/build-lib",
            "runtimeAdapterPath": "runtime/greedrl_runtime_adapter.py",
            "materializedAt": "2026-04-18T00:00:00+00:00",
            "modelArtifactPath": (model_root / "model" / "greedrl-runtime-manifest.json").relative_to(temp_root / "services" / "models").as_posix(),
            "loadedModelFingerprint": fingerprint,
            "fileManifest": greedrl_app._normalized_file_manifest(model_dir),
        }
        if not complete:
            metadata["runtimeAdapterPath"] = ""
        (model_root / "materialization-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    def _write_manifest(self, temp_root: Path, *, fingerprint: str) -> Path:
        runtime_manifest_path = temp_root / "services" / "models" / "materialized" / "greedrl" / "model" / "greedrl-runtime-manifest.json"
        runtime_manifest_bytes = runtime_manifest_path.read_bytes() if runtime_manifest_path.exists() else json.dumps(RUNTIME_MANIFEST, indent=2).encode("utf-8")
        artifact_digest = "sha256:" + hashlib.sha256(runtime_manifest_bytes).hexdigest()
        manifest_path = temp_root / "services" / "models" / "model-manifest.yaml"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            textwrap.dedent(
                f"""
                schemaVersion: model-manifest/v2
                workers:
                  - worker_name: ml-greedrl-worker
                    model_name: greedrl-local
                    model_version: 2026.04.18-v2
                    artifact_digest: {artifact_digest}
                    rollback_artifact_digest: sha256:rollback
                    runtime_image: local/test
                    compatibility_contract_version: dispatch-v2-ml/v1
                    min_supported_java_contract_version: dispatch-v2-java/v1
                    local_model_root: materialized/greedrl
                    local_artifact_path: materialized/greedrl/model/greedrl-runtime-manifest.json
                    materialization_mode: LOCAL_PACKAGE_PROMOTION
                    ready_requires_local_load: true
                    offline_boot_supported: true
                    loaded_model_fingerprint: {fingerprint}
                    source_repository: https://huggingface.co/Cainiao-AI/GreedRL
                    source_ref: 2d5d3bde195dbb5f602908fe42170ffd3ee25c75
                    source_package_requirement: greedrl-community-edition
                    source_python_requirement: ==3.8.*
                    source_build_command: python setup.py build
                    source_test_command: python -c "import greedrl; import greedrl_c"
                    startup_warmup_request:
                      endpoint: /bundle/propose
                      payload:
                        schemaVersion: greedrl-request/v1
                        traceId: warmup-greedrl
                        payload:
                          schemaVersion: greedrl-bundle-feature-vector/v1
                          traceId: warmup-greedrl
                          clusterId: cluster-1
                          workingOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          prioritizedOrderIds:
                            - order-1
                            - order-2
                            - order-3
                          acceptedBoundaryOrderIds:
                            - order-3
                          supportScoreByOrder:
                            order-1: 0.8
                            order-2: 0.7
                            order-3: 0.6
                          bundleMaxSize: 3
                          maxProposals: 2
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return manifest_path


if __name__ == "__main__":
    unittest.main()
