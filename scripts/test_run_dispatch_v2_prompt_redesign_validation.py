import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_prompt_redesign_validation.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_prompt_redesign_validation", MODULE_PATH)
validation_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validation_runner
SPEC.loader.exec_module(validation_runner)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PromptRedesignValidationTest(unittest.TestCase):
    def test_dry_run_prints_planned_cells(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validation_runner.main(["--dry-run", "--stage", "pair-bundle", "--stage", "final-selection"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("[PROMPT VALIDATION] stage-count=2", output)
        self.assertIn("stage=pair-bundle", output)
        self.assertIn("stage=final-selection", output)

    def test_collects_existing_and_validation_evidence_into_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            baseline_root = temp_root / "baseline"
            validation_root = temp_root / "validation"
            output_dir = temp_root / "out"

            benchmark_payload = {
                "baselineId": "C",
                "scenarioPack": "normal-clear",
                "workloadSize": "S",
                "decisionMode": "llm-shadow",
                "executionMode": "controlled",
                "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                "authorityEligible": False,
                "tokenUsageSummary": {"totalTokens": 100},
                "stageFallbackSummary": {"totalFallbacks": 0},
            }
            write_json(baseline_root / "dispatch-quality-normal-clear-s-llm-shadow-controlled-c-20260423-000000.json", benchmark_payload)
            write_json(validation_root / "dispatch-quality-normal-clear-s-llm-shadow-controlled-c-20260423-000001.json", benchmark_payload)

            base_feedback = baseline_root / "feedback" / "normal-clear" / "s" / "controlled" / "llm-shadow" / "c" / "decision-stage"
            validation_feedback = validation_root / "feedback" / "normal-clear" / "s" / "controlled" / "llm-shadow" / "c" / "decision-stage"

            write_json(base_feedback / "llm_request_meta" / "trace-1-pair-bundle.json", {"traceId": "trace-1", "stageName": "pair-bundle"})
            write_json(
                base_feedback / "decision_stage_output" / "trace-1-pair-bundle.json",
                {
                    "traceId": "trace-1",
                    "stageName": "PAIR_BUNDLE",
                    "brainType": "LLM",
                    "assessments": {"summary": "old", "items": [{"id": "bundle-1", "score": 0.7, "selected": True, "rationale": "old"}]},
                    "meta": {"fallbackUsed": False},
                },
            )
            write_json(base_feedback / "decision_stage_join" / "trace-1-pair-bundle.json", {"traceId": "trace-1", "stageName": "PAIR_BUNDLE", "selectedIds": ["bundle-1"], "rejectedIds": ["bundle-2"]})

            write_json(
                validation_feedback / "llm_prompt_spec_trace" / "trace-2-pair-bundle-commit.json",
                {
                    "traceId": "trace-2",
                    "stageName": "pair-bundle",
                    "promptSpecVersion": "decision-stage-prompt-spec/v1",
                    "stagePromptName": "pair-bundle",
                    "stagePromptChecksum": "abc123",
                    "packetTemplateVersion": "decision-stage-packet/v2",
                    "packetTemplateChecksum": "def456",
                    "candidateCountSeen": 12,
                    "comparisonPackCoverage": 1.0,
                    "geospatialCoverage": 1.0,
                    "missingContextFlags": [],
                    "visibilityProfile": "pair-bundle-visibility-v1",
                    "comparisonLens": "PAIR_SUPPORT_LENS",
                    "geospatialLens": "BUNDLE_GEOMETRY_LENS",
                    "fallbackReason": "",
                },
            )
            write_json(
                validation_feedback / "decision_stage_output" / "trace-2-pair-bundle.json",
                {
                    "traceId": "trace-2",
                    "stageName": "PAIR_BUNDLE",
                    "brainType": "LLM",
                    "assessments": {
                        "summary": "new",
                        "reasonCodes": ["ok"],
                        "items": [
                            {
                                "id": "bundle-1",
                                "score": 0.8,
                                "rank": 1,
                                "selected": True,
                                "confidence": 0.9,
                                "reasonCodes": ["fit"],
                                "dominanceReasonCodes": [],
                                "regretToBestAlternative": 0.1,
                                "driverFitSummary": "n/a",
                                "routeVectorRefs": [],
                                "geospatialFlags": ["compact"],
                                "burstSensitivityFlags": [],
                                "rationale": "best",
                            },
                            {
                                "id": "bundle-2",
                                "score": 0.7,
                                "rank": 2,
                                "selected": False,
                                "confidence": 0.7,
                                "reasonCodes": ["spread"],
                                "dominanceReasonCodes": ["dominated"],
                                "regretToBestAlternative": 0.2,
                                "driverFitSummary": "n/a",
                                "routeVectorRefs": [],
                                "geospatialFlags": ["wide"],
                                "burstSensitivityFlags": [],
                                "rationale": "worse",
                            },
                        ],
                    },
                    "meta": {"fallbackUsed": False},
                },
            )
            write_json(validation_feedback / "decision_stage_join" / "trace-2-pair-bundle.json", {"traceId": "trace-2", "stageName": "PAIR_BUNDLE", "selectedIds": ["bundle-1"], "rejectedIds": ["bundle-2"]})

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = validation_runner.main([
                    "--baseline-root", str(baseline_root),
                    "--validation-root", str(validation_root),
                    "--output-dir", str(output_dir),
                    "--stage", "pair-bundle",
                ])

            self.assertEqual(0, exit_code)
            report_path = output_dir / "prompt_redesign_validation_report.md"
            self.assertTrue(report_path.is_file())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("`pair-bundle`", report)
            self.assertIn("`PASS`", report)
            json_reports = sorted(output_dir.glob("prompt-redesign-validation-*.json"))
            self.assertEqual(1, len(json_reports))
            payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
            self.assertEqual("PASS", payload["stageReports"][0]["overallStageVerdict"])
            self.assertEqual(1, payload["stageReports"][0]["baselineEvidenceCount"])
            self.assertEqual(1, payload["stageReports"][0]["validationEvidenceCount"])

    def test_rerun_cells_calls_benchmark_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            calls: list[tuple[str, str]] = []

            def fake_run_validation_cell(cell, out_dir, runner=None):
                calls.append((cell.stage, str(out_dir)))
                write_json(
                    output_dir / "live" / f"dispatch-quality-{cell.scenario_pack}-{cell.size.lower()}-{cell.decision_mode}-controlled-c-20260423-000000.json",
                    {
                        "baselineId": cell.baseline,
                        "scenarioPack": cell.scenario_pack,
                        "workloadSize": cell.size,
                        "decisionMode": cell.decision_mode,
                        "executionMode": cell.execution_mode,
                        "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                        "authorityEligible": False,
                        "tokenUsageSummary": {"totalTokens": 10},
                        "stageFallbackSummary": {"totalFallbacks": 0},
                    },
                )
                feedback_root = output_dir / "live" / "feedback" / cell.scenario_pack / cell.size.lower() / cell.execution_mode / cell.decision_mode / "c" / "decision-stage"
                write_json(
                    feedback_root / "llm_prompt_spec_trace" / f"trace-{cell.stage}-{cell.stage}-commit.json",
                    {
                        "traceId": f"trace-{cell.stage}",
                        "stageName": cell.stage,
                        "promptSpecVersion": "decision-stage-prompt-spec/v1",
                        "stagePromptName": cell.stage,
                        "stagePromptChecksum": f"{cell.stage}-prompt",
                        "packetTemplateVersion": "decision-stage-packet/v2",
                        "packetTemplateChecksum": f"{cell.stage}-packet",
                        "candidateCountSeen": 3,
                        "comparisonPackCoverage": 1.0,
                        "geospatialCoverage": 1.0,
                        "missingContextFlags": [],
                    },
                )
                write_json(
                    feedback_root / "decision_stage_output" / f"trace-{cell.stage}-{cell.stage}.json",
                    {
                        "traceId": f"trace-{cell.stage}",
                        "stageName": cell.stage.replace("-", "_").upper(),
                        "brainType": "LLM",
                        "assessments": {
                            "summary": "ok",
                            "items": [
                                {"id": "a", "score": 0.8, "rank": 1, "selected": True, "confidence": 0.8, "reasonCodes": [], "dominanceReasonCodes": [], "regretToBestAlternative": 0.0, "driverFitSummary": "ok", "routeVectorRefs": [], "geospatialFlags": [], "burstSensitivityFlags": [], "rationale": "ok"},
                                {"id": "b", "score": 0.7, "rank": 2, "selected": False, "confidence": 0.7, "reasonCodes": [], "dominanceReasonCodes": [], "regretToBestAlternative": 0.1, "driverFitSummary": "ok", "routeVectorRefs": [], "geospatialFlags": [], "burstSensitivityFlags": [], "rationale": "ok"},
                            ],
                        },
                        "meta": {"fallbackUsed": False},
                    },
                )
                write_json(feedback_root / "decision_stage_join" / f"trace-{cell.stage}-{cell.stage}.json", {"traceId": f"trace-{cell.stage}", "stageName": cell.stage.replace("-", "_").upper(), "selectedIds": ["a"], "rejectedIds": ["b"]})
                return 0

            original_run_validation_cell = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = validation_runner.main([
                        "--output-dir", str(output_dir),
                        "--stage", "pair-bundle",
                        "--stage", "final-selection",
                        "--rerun-cells",
                    ])
            finally:
                validation_runner.run_validation_cell = original_run_validation_cell

            self.assertEqual(0, exit_code)
            self.assertEqual(2, len(calls))
            self.assertTrue((output_dir / "prompt_redesign_validation_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
