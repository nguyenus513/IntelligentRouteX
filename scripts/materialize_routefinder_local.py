from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


MATERIALIZER_SCHEMA_VERSION = "routefinder-materialization/v2"
PROMOTED_ARTIFACT_SCHEMA_VERSION = "routefinder-promoted-artifact/v2"
MATERIALIZER_VERSION = "routefinder-materializer/v1"
DEFAULT_SOURCE_REPOSITORY = "https://github.com/ai4co/routefinder.git"
DEFAULT_SOURCE_REF = "fe0e45b6df118af03c5f42db8b93a351f7629131"
DEFAULT_SOURCE_CHECKPOINT_PATH = "checkpoints/100/rf-transformer.ckpt"
DEFAULT_SOURCE_DOWNLOAD_COMMAND = "python scripts/download_hf.py --models --no-data"
DEFAULT_SOURCE_TEST_COMMAND = "python test.py --checkpoint checkpoints/100/rf-transformer.ckpt"
PROMOTED_MODEL_NAME = "routefinder-local"
PROMOTED_MODEL_VERSION = "2026.04.18-v2"
ML_CONTRACT_VERSION = "dispatch-v2-ml/v1"
JAVA_CONTRACT_VERSION = "dispatch-v2-java/v1"
PROMOTED_RUNTIME_PARAMETERS = {
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_file_manifest(model_directory: Path) -> list[dict]:
    entries: list[dict] = []
    for file_path in sorted(path for path in model_directory.rglob("*") if path.is_file()):
        entries.append(
            {
                "path": file_path.relative_to(model_directory).as_posix(),
                "size": file_path.stat().st_size,
                "sha256": _sha256(file_path),
            }
        )
    return entries


def _loaded_model_fingerprint(model_directory: Path) -> str:
    normalized = json.dumps(_normalized_file_manifest(model_directory), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)


def _remove_tree(path: Path) -> None:
    def onerror(func, target, exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=onerror)


def _create_venv(venv_path: Path, python_executable: str) -> Path:
    if not venv_path.exists():
        _run([python_executable, "-m", "venv", str(venv_path)])
    return venv_path / ("Scripts" if sys.platform.startswith("win") else "bin") / "python"


def _venv_env(venv_path: Path) -> dict[str, str]:
    env = dict(**os.environ)
    env["VIRTUAL_ENV"] = str(venv_path)
    scripts_dir = venv_path / ("Scripts" if sys.platform.startswith("win") else "bin")
    env["PATH"] = str(scripts_dir) + os.pathsep + env.get("PATH", "")
    return env


def _clone_checkout(source_repository: str, source_ref: str, source_dir: Path) -> str:
    if source_dir.exists():
        _remove_tree(source_dir)
    _run(["git", "clone", source_repository, str(source_dir)])
    _run(["git", "checkout", source_ref], cwd=source_dir)
    return _run(["git", "rev-parse", "HEAD"], cwd=source_dir).stdout.strip()


def _relative_to(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _promoted_artifact(source_repository: str,
                       source_ref: str,
                       source_commit: str,
                       source_checkpoint_path: str,
                       source_checkpoint_digest: str,
                       local_checkpoint_path: str) -> dict:
    return {
        "schemaVersion": PROMOTED_ARTIFACT_SCHEMA_VERSION,
        "modelName": PROMOTED_MODEL_NAME,
        "modelVersion": PROMOTED_MODEL_VERSION,
        "compatibilityContractVersion": ML_CONTRACT_VERSION,
        "minSupportedJavaContractVersion": JAVA_CONTRACT_VERSION,
        "sourceRepository": source_repository,
        "sourceRef": source_ref,
        "sourceCommit": source_commit,
        "sourceCheckpointPath": source_checkpoint_path,
        "sourceCheckpointDigest": source_checkpoint_digest,
        "localCheckpointPath": local_checkpoint_path,
        "localCheckpointDigest": source_checkpoint_digest,
        "inferenceBackend": "checkpoint-present-json-policy",
        **PROMOTED_RUNTIME_PARAMETERS,
    }


def _write_promoted_output(repo_root: Path,
                           temp_output_root: Path,
                           final_output_root: Path,
                           source_repository: str,
                           source_ref: str,
                           source_commit: str,
                           source_checkout_dir: Path,
                           source_checkpoint_path: str,
                           source_download_command: str,
                           source_test_command: str) -> tuple[Path, Path, str, str]:
    model_directory = temp_output_root / "model"
    model_directory.mkdir(parents=True, exist_ok=True)
    promoted_artifact_path = model_directory / "routefinder-model.json"
    checkpoint_path = source_checkout_dir / Path(source_checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"RouteFinder checkpoint not found after download: {checkpoint_path}")
    checkpoint_digest = "sha256:" + _sha256(checkpoint_path)
    local_checkpoint_path = Path(source_checkpoint_path).as_posix()
    promoted_checkpoint_path = model_directory / local_checkpoint_path
    promoted_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint_path, promoted_checkpoint_path)
    promoted_artifact = _promoted_artifact(
        source_repository,
        source_ref,
        source_commit,
        source_checkpoint_path,
        checkpoint_digest,
        local_checkpoint_path,
    )
    promoted_artifact_path.write_text(json.dumps(promoted_artifact, indent=2) + "\n", encoding="utf-8")
    loaded_fingerprint = _loaded_model_fingerprint(model_directory)
    materialization_metadata = {
        "schemaVersion": MATERIALIZER_SCHEMA_VERSION,
        "materializerVersion": MATERIALIZER_VERSION,
        "materializationMode": "HF_CHECKPOINT_PROMOTION",
        "sourceRepository": source_repository,
        "sourceRef": source_ref,
        "sourceCommit": source_commit,
        "sourceCheckoutPath": _relative_to(source_checkout_dir, repo_root),
        "sourceDownloadCommand": source_download_command,
        "sourceTestCommand": source_test_command,
        "sourceCheckpointPath": source_checkpoint_path,
        "sourceCheckpointDigest": checkpoint_digest,
        "materializedAt": datetime.now(timezone.utc).isoformat(),
        "modelArtifactPath": (final_output_root / "model" / promoted_artifact_path.name).relative_to(
            repo_root / "services" / "models").as_posix(),
        "loadedModelFingerprint": loaded_fingerprint,
        "fileManifest": _normalized_file_manifest(model_directory),
    }
    metadata_path = temp_output_root / "materialization-metadata.json"
    metadata_path.write_text(json.dumps(materialization_metadata, indent=2) + "\n", encoding="utf-8")
    artifact_digest = "sha256:" + _sha256(promoted_artifact_path)
    return promoted_artifact_path, metadata_path, artifact_digest, loaded_fingerprint


def _atomic_promote(temp_output_root: Path, output_root: Path) -> None:
    backup_root = output_root.parent / f"{output_root.name}.bak"
    if backup_root.exists():
        _remove_tree(backup_root)
    if output_root.exists():
        shutil.move(str(output_root), str(backup_root))
    try:
        shutil.move(str(temp_output_root), str(output_root))
    except Exception:
        if output_root.exists():
            _remove_tree(output_root)
        if backup_root.exists():
            shutil.move(str(backup_root), str(output_root))
        raise
    else:
        if backup_root.exists():
            _remove_tree(backup_root)


def materialize_routefinder(*,
                            repo_root: Path,
                            output_root: Path,
                            venv_path: Path,
                            staging_root: Path,
                            python_executable: str,
                            source_repository: str,
                            source_ref: str,
                            source_checkpoint_path: str,
                            source_download_command: str,
                            source_test_command: str,
                            run_upstream_test: bool) -> dict:
    source_checkout_dir = staging_root / "source"
    temp_output_root = staging_root / "promoted-output"
    if staging_root.exists():
        _remove_tree(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    venv_python = _create_venv(venv_path, python_executable)
    venv_env = _venv_env(venv_path)
    source_commit = _clone_checkout(source_repository, source_ref, source_checkout_dir)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], env=venv_env)
    _run([str(venv_python), "-m", "pip", "install", "-e", "."], cwd=source_checkout_dir, env=venv_env)
    _run([str(venv_python), "scripts/download_hf.py", "--models", "--no-data"], cwd=source_checkout_dir, env=venv_env)
    checkpoint_path = source_checkout_dir / Path(source_checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"RouteFinder checkpoint not materialized: {checkpoint_path}")
    if run_upstream_test:
        _run([str(venv_python), "test.py", "--checkpoint", source_checkpoint_path, "--size", "100", "--device", "cpu"], cwd=source_checkout_dir, env=venv_env)
    promoted_artifact_path, metadata_path, artifact_digest, loaded_model_fingerprint = _write_promoted_output(
        repo_root,
        temp_output_root,
        output_root,
        source_repository,
        source_ref,
        source_commit,
        source_checkout_dir,
        source_checkpoint_path,
        source_download_command,
        source_test_command,
    )
    _atomic_promote(temp_output_root, output_root)
    return {
        "outputRoot": str(output_root),
        "modelArtifactPath": str(output_root / "model" / promoted_artifact_path.name),
        "materializationMetadataPath": str(output_root / metadata_path.name),
        "sourceCommit": source_commit,
        "artifactDigest": artifact_digest,
        "loadedModelFingerprint": loaded_model_fingerprint,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        default=str(repo_root / "services" / "models" / "materialized" / "routefinder"),
    )
    parser.add_argument(
        "--venv-path",
        default=str(repo_root / "build" / "materialization" / "routefinder-venv"),
    )
    parser.add_argument(
        "--staging-root",
        default=str(repo_root / "build" / "materialization" / "routefinder"),
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
    )
    parser.add_argument(
        "--source-repository",
        default=DEFAULT_SOURCE_REPOSITORY,
    )
    parser.add_argument(
        "--source-ref",
        default=DEFAULT_SOURCE_REF,
    )
    parser.add_argument(
        "--source-checkpoint-path",
        default=DEFAULT_SOURCE_CHECKPOINT_PATH,
    )
    parser.add_argument(
        "--source-download-command",
        default=DEFAULT_SOURCE_DOWNLOAD_COMMAND,
    )
    parser.add_argument(
        "--source-test-command",
        default=DEFAULT_SOURCE_TEST_COMMAND,
    )
    parser.add_argument("--run-upstream-test", dest="run_upstream_test", action="store_true", default=False)
    parser.add_argument("--no-run-upstream-test", dest="run_upstream_test", action="store_false")
    args = parser.parse_args()

    result = materialize_routefinder(
        repo_root=repo_root,
        output_root=Path(args.output_root).resolve(),
        venv_path=Path(args.venv_path).resolve(),
        staging_root=Path(args.staging_root).resolve(),
        python_executable=args.python_executable,
        source_repository=args.source_repository,
        source_ref=args.source_ref,
        source_checkpoint_path=args.source_checkpoint_path,
        source_download_command=args.source_download_command,
        source_test_command=args.source_test_command,
        run_upstream_test=args.run_upstream_test,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
