import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "build_dispatch_v2_student_dataset.py"
SPEC = importlib.util.spec_from_file_location("build_dispatch_v2_student_dataset", MODULE_PATH)
dataset_builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(dataset_builder)


class BuildDispatchV2StudentDatasetTest(unittest.TestCase):
    def test_builder_writes_expected_jsonl_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            feedback_root = Path(temp_dir) / "feedback" / "normal-clear" / "s" / "legacy" / "phase-1"
            output_dir = Path(temp_dir) / "dataset"
            base = feedback_root / "decision-stage"
            for family in (
                "decision_stage_input",
                "decision_stage_output",
                "decision_stage_join",
                "dispatch_execution",
                "dispatch_outcome",
                "route_leg_vector_trace",
                "route_vector_summary_trace",
            ):
                (base / family).mkdir(parents=True, exist_ok=True)

            (base / "decision_stage_input" / "trace-1-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-1", "tickId": "tick-1", "stageName": "pair-bundle", "decisionMode": "legacy"}),
                encoding="utf-8",
            )
            (base / "decision_stage_output" / "trace-1-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-1", "tickId": "tick-1", "stageName": "pair-bundle", "brainType": "LEGACY", "selectedIds": ["bundle-1"], "decisionMode": "legacy"}),
                encoding="utf-8",
            )
            (base / "decision_stage_join" / "trace-1-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-1", "tickId": "tick-1", "stageName": "pair-bundle", "brainType": "LEGACY", "selectedIds": ["bundle-1"], "actualSelectedIds": ["bundle-1"], "decisionMode": "legacy"}),
                encoding="utf-8",
            )
            (base / "dispatch_execution" / "trace-1-dispatch-executor.json").write_text(
                json.dumps({"assignmentIds": ["assignment-1"], "decisionMode": "legacy"}),
                encoding="utf-8",
            )
            (base / "dispatch_outcome" / "trace-1.json").write_text(
                json.dumps({"traceId": "trace-1", "selectedProposalIds": ["proposal-1"], "decisionMode": "legacy"}),
                encoding="utf-8",
            )
            (base / "route_leg_vector_trace" / "trace-1-proposal-1.json").write_text(
                json.dumps({
                    "schemaVersion": "route-leg-vector-trace/v1",
                    "traceId": "trace-1",
                    "proposalId": "proposal-1",
                    "legs": [{"fromStopId": "a", "toStopId": "b"}],
                    "decisionMode": "legacy",
                }),
                encoding="utf-8",
            )
            (base / "route_vector_summary_trace" / "trace-1-proposal-1.json").write_text(
                json.dumps({"traceId": "trace-1", "proposalId": "proposal-1", "legCount": 2, "decisionMode": "legacy"}),
                encoding="utf-8",
            )

            exit_code = dataset_builder.main([
                "--feedback-root", str(feedback_root),
                "--output-dir", str(output_dir),
                "--authority-mode", "legacy",
                "--stage", "pair-bundle",
                "--decision-mode", "legacy",
                "--scenario-pack", "normal-clear",
                "--authority-phase", "phase-1",
            ])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "stage_inputs.jsonl").is_file())
            self.assertTrue((output_dir / "stage_outputs.jsonl").is_file())
            self.assertTrue((output_dir / "stage_joins.jsonl").is_file())
            self.assertTrue((output_dir / "dispatch_execution.jsonl").is_file())
            self.assertTrue((output_dir / "dispatch_outcomes.jsonl").is_file())
            self.assertTrue((output_dir / "route_vectors.jsonl").is_file())
            manifest = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("legacy", manifest["authorityMode"])
            self.assertEqual(["pair-bundle"], manifest["filters"]["stages"])
            self.assertEqual("normal-clear", manifest["filters"]["scenarioPack"])
            self.assertEqual(1, manifest["counts"]["stage_inputs"])
            self.assertEqual(1, manifest["counts"]["route_vectors"])
            route_vectors = (output_dir / "route_vectors.jsonl").read_text(encoding="utf-8")
            self.assertIn("\"legPayloads\": [[{\"fromStopId\": \"a\", \"toStopId\": \"b\"}]]", route_vectors)

    def test_builder_discovers_nested_feedback_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            aggregate_root = Path(temp_dir) / "feedback"
            feedback_root = aggregate_root / "normal-clear" / "s" / "controlled" / "legacy" / "c"
            output_dir = Path(temp_dir) / "dataset"
            base = feedback_root / "decision-stage"
            for family in (
                "decision_stage_input",
                "decision_stage_output",
                "decision_stage_join",
                "dispatch_execution",
                "dispatch_outcome",
                "route_leg_vector_trace",
                "route_vector_summary_trace",
            ):
                (base / family).mkdir(parents=True, exist_ok=True)

            (base / "decision_stage_input" / "trace-2-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-2", "tickId": "tick-2", "stageName": "pair-bundle", "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )
            (base / "decision_stage_output" / "trace-2-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-2", "tickId": "tick-2", "stageName": "pair-bundle", "brainType": "LEGACY", "selectedIds": ["bundle-2"], "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )
            (base / "decision_stage_join" / "trace-2-pair-bundle.json").write_text(
                json.dumps({"traceId": "trace-2", "tickId": "tick-2", "stageName": "pair-bundle", "brainType": "LEGACY", "selectedIds": ["bundle-2"], "actualSelectedIds": ["bundle-2"], "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )
            (base / "dispatch_execution" / "trace-2-dispatch-executor.json").write_text(
                json.dumps({"assignmentIds": ["assignment-2"], "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )
            (base / "dispatch_outcome" / "trace-2-dispatch-result.json").write_text(
                json.dumps({"selectedProposalIds": ["proposal-2"], "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )
            (base / "route_leg_vector_trace" / "trace-2-proposal-2.json").write_text(
                json.dumps({
                    "schemaVersion": "route-leg-vector-trace/v1",
                    "traceId": "trace-2",
                    "proposalId": "proposal-2",
                    "legs": [{"fromStopId": "x", "toStopId": "y"}],
                    "decisionMode": "legacy",
                    "authorityPhase": "c",
                }),
                encoding="utf-8",
            )
            (base / "route_vector_summary_trace" / "trace-2-proposal-2.json").write_text(
                json.dumps({"traceId": "trace-2", "proposalId": "proposal-2", "legCount": 1, "decisionMode": "legacy", "authorityPhase": "c"}),
                encoding="utf-8",
            )

            exit_code = dataset_builder.main([
                "--feedback-root", str(aggregate_root),
                "--output-dir", str(output_dir),
                "--authority-mode", "legacy",
                "--decision-mode", "legacy",
                "--scenario-pack", "normal-clear",
                "--authority-phase", "c",
                "--route-vector-availability", "required",
            ])

            self.assertEqual(0, exit_code)
            manifest = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["counts"]["stage_inputs"])
            self.assertEqual(1, manifest["counts"]["route_vectors"])
            self.assertEqual(str(feedback_root), manifest["discoveredFeedbackRoots"][0])


if __name__ == "__main__":
    unittest.main()
