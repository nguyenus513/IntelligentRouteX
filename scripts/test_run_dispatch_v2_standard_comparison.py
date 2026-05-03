import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_standard_comparison.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_standard_comparison", MODULE_PATH)
standard_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = standard_runner
SPEC.loader.exec_module(standard_runner)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def benchmark_payload(**overrides) -> dict:
    payload = {
        "baselineId": "C",
        "scenarioPack": "normal-clear",
        "workloadSize": "S",
        "executionMode": "controlled",
        "decisionMode": "legacy",
        "promptFamily": "v2",
        "cellStartedAt": "2026-04-24T00:00:00+00:00",
        "cellCompletedAt": "2026-04-24T00:00:01+00:00",
        "metrics": {
            "executedAssignmentCount": 2,
            "conflictFreeAssignments": True,
            "executionValid": True,
            "robustUtilityAverage": 0.75,
            "routeCostQuality": 1.2,
            "driverEntryQuality": 0.8,
            "workerFallbackRate": 0.0,
        },
        "stageFallbackSummary": {"totalFallbacks": 0, "latestFallbackReasonByStage": {}},
        "routeVectorMetrics": {"proposalCount": 4, "geometryCoverage": 0.9},
        "tokenUsageSummary": {"requestCount": 0, "totalTokens": 0},
        "workerStatusSnapshot": {"ml-routefinder-worker": {"device": "cuda:0"}},
    }
    payload.update(overrides)
    return payload


class StandardComparisonRunnerTest(unittest.TestCase):
    def test_local_minimum_expands_four_scenarios_by_default_profiles(self) -> None:
        cells = standard_runner.planned_cells("local-minimum")

        self.assertEqual(12, len(cells))
        self.assertEqual("normal-clear/S/heuristic-only", cells[0].cell_id)
        self.assertEqual("forecast-heavy/S/full-adaptive", cells[-1].cell_id)

    def test_profile_mapping_builds_full_adaptive_legacy_command(self) -> None:
        cell = standard_runner.StandardCell(
            "traffic-shock",
            "S",
            standard_runner.PROFILE_SPECS["full-adaptive"],
        )

        command = standard_runner.benchmark_command(cell, Path("out"))

        self.assertIn("--baseline", command)
        self.assertIn("C", command)
        self.assertIn("--decision-mode", command)
        self.assertIn("legacy", command)
        self.assertIn("--profile", command)
        self.assertIn("dispatch-v2-full-adaptive", command)
        self.assertEqual(0, command.count("--authoritative-stage"))

    def test_classifies_valid_fallback_and_invalid_artifacts(self) -> None:
        self.assertEqual(("PASS", ("quality-artifact-valid",)), standard_runner.classify_artifact(benchmark_payload(timeoutPhase="NONE")))

        fallback_payload = benchmark_payload(
            metrics={
                "executedAssignmentCount": 2,
                "conflictFreeAssignments": True,
                "executionValid": True,
                "workerFallbackRate": 0.25,
            }
        )
        fallback_verdict, fallback_reasons = standard_runner.classify_artifact(fallback_payload)
        self.assertEqual("PASS_WITH_LIMITS", fallback_verdict)
        self.assertIn("fallback-or-degrade-observed", fallback_reasons)

        invalid_payload = benchmark_payload(metrics={"conflictFreeAssignments": False, "executionValid": True})
        self.assertEqual("FAIL", standard_runner.classify_artifact(invalid_payload)[0])

    def test_extract_failure_classes_normalizes_promotion_blockers(self) -> None:
        reasons = standard_runner.extract_failure_classes(benchmark_payload(
            promotionBlockers=[
                {"stageName": "route-generation", "blockerReasons": ["route-vector-coverage-below-1.0"]}
            ]
        ))

        self.assertEqual(("route-generation:route-vector-coverage-below-1.0",), reasons)

    def test_llm_profiles_are_disabled_by_policy(self) -> None:
        self.assertFalse(hasattr(standard_runner, "LLM_PROFILES"))
        self.assertNotIn("llm-shadow", standard_runner.PROFILE_SPECS)
        self.assertNotIn("llm-authoritative-gated", standard_runner.PROFILE_SPECS)

    def test_run_standard_cell_collects_artifact_and_decision_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            cell = standard_runner.StandardCell(
                "normal-clear",
                "S",
                standard_runner.PROFILE_SPECS["ml-only"],
            )

            def fake_runner(command, cwd=None, text=None, check=None, timeout=None):
                self.assertEqual(180, timeout)
                output_dir = Path(command[command.index("--output-dir") + 1])
                artifact = output_dir / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260424-000000.json"
                write_json(artifact, benchmark_payload())
                decision_log = output_dir / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-log" / "quality-normal-clear-s-legacy-v2-c.json"
                write_json(decision_log, {
                    "stageLatencies": [{"stageName": "route-proposal-pool", "elapsedMs": 42}],
                    "mlStageMetadata": [{"sourceModel": "routefinder-local", "latencyMs": 7, "fallbackUsed": False}],
                })
                return type("Completed", (), {"returncode": 0})()

            result = standard_runner.run_standard_cell(cell, output_root, True, "ready", runner=fake_runner)
            row = standard_runner.cell_report_row(result)

            self.assertEqual("PASS", result.verdict)
            self.assertEqual(1000, row["totalLatencyMs"])
            self.assertEqual(42, row["stageLatencies"]["route-proposal-pool"])
            self.assertEqual(1, row["mlInvocations"]["routefinder-local"]["count"])

    def test_write_reports_emits_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = {
                "scenarioPack": "normal-clear",
                "size": "S",
                "profile": "ml-only",
                "verdict": "PASS",
                "totalLatencyMs": 1000,
                "executedAssignmentCount": 2,
                "robustUtilityAverage": 0.75,
                "routeProposalCount": 4,
                "stageFallbackCount": 0,
                "llmRequestCount": 0,
                "verdictReasons": ["quality-artifact-valid"],
            }

            json_path, markdown_path = standard_runner.write_reports(
                [row],
                Path(temp_dir),
                "ml-only-4case",
                {"ready": True, "reason": "not-required"},
            )

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["verdictCounts"]["PASS"])
            self.assertIn("Dispatch V2 Standard Comparison", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
