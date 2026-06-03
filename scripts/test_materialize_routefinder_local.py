import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parent / "materialize_routefinder_local.py"
SPEC = importlib.util.spec_from_file_location("materialize_routefinder_local", MODULE_PATH)
materializer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(materializer)


class RouteFinderMaterializerTest(unittest.TestCase):
    def test_promoted_output_records_upstream_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "repo"
            source_dir = temp_root / "source"
            temp_output_root = temp_root / "promoted"
            checkpoint_path = source_dir / "checkpoints" / "100"
            checkpoint_path.mkdir(parents=True, exist_ok=True)
            (checkpoint_path / "rf-transformer.ckpt").write_bytes(b"checkpoint")

            promoted_artifact_path, metadata_path, artifact_digest, fingerprint = materializer._write_promoted_output(
                repo_root,
                temp_output_root,
                repo_root / "services" / "models" / "materialized" / "routefinder",
                "https://github.com/ai4co/routefinder.git",
                "fe0e45b6df118af03c5f42db8b93a351f7629131",
                "fe0e45b6df118af03c5f42db8b93a351f7629131",
                source_dir,
                "checkpoints/100/rf-transformer.ckpt",
                "python scripts/download_hf.py --models --no-data",
                "python test.py --checkpoint checkpoints/100/rf-transformer.ckpt",
            )

            artifact = json.loads(promoted_artifact_path.read_text(encoding="utf-8"))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual("routefinder-promoted-artifact/v2", artifact["schemaVersion"])
            self.assertEqual("https://github.com/ai4co/routefinder.git", artifact["sourceRepository"])
            self.assertEqual("checkpoints/100/rf-transformer.ckpt", artifact["sourceCheckpointPath"])
            self.assertEqual("checkpoints/100/rf-transformer.ckpt", artifact["localCheckpointPath"])
            self.assertEqual(artifact["sourceCheckpointDigest"], artifact["localCheckpointDigest"])
            self.assertEqual("checkpoint-present-json-policy", artifact["inferenceBackend"])
            self.assertTrue((temp_output_root / "model" / "checkpoints" / "100" / "rf-transformer.ckpt").exists())
            self.assertIn("checkpoints/100/rf-transformer.ckpt", [entry["path"] for entry in metadata["fileManifest"]])
            self.assertTrue(artifact_digest.startswith("sha256:"))
            self.assertEqual(fingerprint, metadata["loadedModelFingerprint"])
            self.assertEqual("fe0e45b6df118af03c5f42db8b93a351f7629131", metadata["sourceCommit"])

    def test_atomic_promote_restores_previous_output_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output_root = temp_root / "materialized"
            output_root.mkdir(parents=True, exist_ok=True)
            (output_root / "old.txt").write_text("old", encoding="utf-8")
            temp_output_root = temp_root / "promoted-temp"
            temp_output_root.mkdir(parents=True, exist_ok=True)
            (temp_output_root / "new.txt").write_text("new", encoding="utf-8")

            original_move = materializer.shutil.move
            move_calls = {"count": 0}

            def failing_second_move(src, dst):
                move_calls["count"] += 1
                if move_calls["count"] == 2:
                    raise RuntimeError("boom")
                return original_move(src, dst)

            with patch.object(materializer.shutil, "move", side_effect=failing_second_move):
                with self.assertRaises(RuntimeError):
                    materializer._atomic_promote(temp_output_root, output_root)

            self.assertTrue((output_root / "old.txt").exists())

    def test_materialize_routefinder_fails_when_checkpoint_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "repo"
            output_root = repo_root / "services" / "models" / "materialized" / "routefinder"
            venv_path = temp_root / "venv"
            staging_root = temp_root / "staging"
            source_dir = staging_root / "source"

            def fake_run(command, *, cwd=None, env=None):
                return type("Completed", (), {"stdout": "", "stderr": ""})()

            def fake_clone(source_repository, source_ref, target_dir):
                target_dir.mkdir(parents=True, exist_ok=True)
                return "fe0e45b6df118af03c5f42db8b93a351f7629131"

            with patch.object(materializer, "_run", side_effect=fake_run), patch.object(
                    materializer, "_clone_checkout", side_effect=fake_clone):
                with self.assertRaises(FileNotFoundError):
                    materializer.materialize_routefinder(
                        repo_root=repo_root,
                        output_root=output_root,
                        venv_path=venv_path,
                        staging_root=staging_root,
                        python_executable="python",
                        source_repository="https://github.com/ai4co/routefinder.git",
                        source_ref="fe0e45b6df118af03c5f42db8b93a351f7629131",
                        source_checkpoint_path="checkpoints/100/rf-transformer.ckpt",
                        source_download_command="python scripts/download_hf.py --models --no-data",
                        source_test_command="python test.py --checkpoint checkpoints/100/rf-transformer.ckpt",
                        run_upstream_test=False,
                    )

            self.assertFalse(output_root.exists())
            self.assertFalse((source_dir / "checkpoints" / "100" / "rf-transformer.ckpt").exists())


if __name__ == "__main__":
    unittest.main()
