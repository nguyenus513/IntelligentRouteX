import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_module(name: str, filename: str):
    module_path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_logs = load_module("validate_distillation_logs", "validate_distillation_logs.py")
silver_builder = load_module("build_silver_from_bronze", "build_silver_from_bronze.py")
gold_builder = load_module("build_gold_distillation_datasets", "build_gold_distillation_datasets.py")


class DispatchV2HarvestPipelineTest(unittest.TestCase):
    def test_bronze_to_gold_pipeline_builds_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bronze_root = Path(temp_dir) / "bronze"
            silver_root = Path(temp_dir) / "silver"
            gold_root = Path(temp_dir) / "gold"
            families = (
                "harvest-run-manifest",
                "decision-stage-input",
                "decision-stage-output",
                "decision-stage-join",
                "dispatch-execution",
                "dispatch-outcome",
                "geo-tile-selection-trace",
                "tile-feature-trace",
                "bundle-geometry-trace",
                "driver-pickup-fit-trace",
                "route-vector-trace",
                "route-stop-trace",
                "traffic-context-trace",
                "tabular-teacher-trace",
                "greedrl-teacher-trace",
                "routefinder-teacher-trace",
                "forecast-teacher-trace",
            )
            for family in families:
                (bronze_root / family).mkdir(parents=True, exist_ok=True)

            run_id = "trace-1"
            def write_row(family: str, row: dict) -> None:
                target = bronze_root / family / f"{run_id}.jsonl"
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row) + "\n")

            write_row("harvest-run-manifest", {"schemaVersion": "harvest-run-manifest/v1", "rowType": "stage", "traceId": run_id, "runId": run_id})
            write_row("decision-stage-input", {"schemaVersion": "bronze-candidate-row/v1", "rowType": "candidate", "traceId": run_id, "runId": run_id, "stageName": "pair-bundle", "entityType": "bundle", "entityId": "bundle-1", "candidateId": "bundle:bundle-1", "score": 0.7})
            write_row("decision-stage-output", {"schemaVersion": "bronze-candidate-row/v1", "rowType": "candidate", "traceId": run_id, "runId": run_id, "stageName": "pair-bundle", "entityType": "bundle", "entityId": "bundle-1", "candidateId": "bundle:bundle-1", "selected": True, "score": 0.9, "confidence": 0.8})
            write_row("decision-stage-join", {"schemaVersion": "bronze-candidate-row/v1", "rowType": "candidate", "traceId": run_id, "runId": run_id, "stageName": "pair-bundle", "entityType": "bundle", "entityId": "bundle-1", "candidateId": "bundle:bundle-1", "selected": True, "downstreamChosen": True})
            write_row("dispatch-execution", {"schemaVersion": "dispatch-execution-bronze/v1", "rowType": "stage", "traceId": run_id, "runId": run_id})
            write_row("dispatch-outcome", {"schemaVersion": "dispatch-outcome-bronze/v1", "rowType": "stage", "traceId": run_id, "runId": run_id, "labelQuality": "SIMULATED_STRONG", "delivered": True})
            for family in ("geo-tile-selection-trace", "tile-feature-trace", "bundle-geometry-trace", "driver-pickup-fit-trace", "route-vector-trace", "route-stop-trace", "traffic-context-trace", "tabular-teacher-trace", "greedrl-teacher-trace", "routefinder-teacher-trace", "forecast-teacher-trace"):
                write_row(family, {"schemaVersion": f"{family}/v1", "rowType": "candidate", "traceId": run_id, "runId": run_id, "stageName": "pair-bundle", "entityType": "bundle", "entityId": "bundle-1", "candidateId": "bundle:bundle-1"})

            validate_result = validate_logs.validate(bronze_root)
            self.assertGreater(validate_result["candidateRows"], 0)

            silver_exit = silver_builder.main(["--bronze-root", str(bronze_root), "--output-dir", str(silver_root)])
            self.assertEqual(0, silver_exit)
            self.assertTrue((silver_root / "decision_stage_join.jsonl").is_file())

            gold_exit = gold_builder.main(["--silver-root", str(silver_root), "--output-dir", str(gold_root)])
            self.assertEqual(0, gold_exit)
            self.assertTrue((gold_root / "unified_dispatch_distillation.parquet").is_file())
            self.assertTrue((gold_root / "selection_score.parquet").is_file())


if __name__ == "__main__":
    unittest.main()
