import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_benchmark", MODULE_PATH)
benchmark_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark_runner)


class RunDispatchBenchmarkTest(unittest.TestCase):
    def test_dry_run_prints_planned_matrix(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = benchmark_runner.main(["--scenario-pack", "normal-clear", "--size", "S", "--dry-run"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("[MATRIX]", output)
        self.assertIn("scenario-pack=normal-clear", output)
        self.assertIn("decision-mode=legacy", output)
        self.assertIn("prompt-family=v2", output)
        self.assertIn("authoritative-stages=[]", output)
        self.assertIn("authority=false", output)
        self.assertIn("profile=default", output)

    def test_runner_collects_json_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_runner(command, cwd=None, text=None, check=None, env=None):
                stem = "dispatch-quality-normal-clear-s-controlled-a-20260418-000000"
                (output_dir / f"{stem}.json").write_text(
                    json.dumps({
                        "baselineId": "A",
                        "scenarioPack": "normal-clear",
                        "workloadSize": "S",
                        "decisionMode": "legacy",
                        "promptFamily": "v2",
                        "authoritativeStages": [],
                        "executionMode": "controlled",
                        "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                        "authorityEligible": False,
                        "metrics": {"selectedProposalCount": 1, "executedAssignmentCount": 1, "robustUtilityAverage": 0.5},
                        "decisionAgreement": {"overallExactMatchRate": 0.0},
                        "bundleDiversity": {"candidateCount": 12, "retainedCount": 8, "familyDiversityCount": 3, "lateRiskRescueCandidateCount": 2, "activeRouteAddonCandidateCount": 1},
                        "selectorTelemetry": {"mode": "CP_SAT_TIMEOUT_INCUMBENT", "poolInputCount": 12, "poolReducedCount": 8, "poolRejectedCount": 4, "fallbackLevel": "CP_SAT_TIMEOUT_INCUMBENT", "selectorMaxPoolSize": 256, "selectorPoolCapApplied": True, "selectorPoolCapObjectiveLoss": 0.0, "acceptanceGatePassed": True},
                        "objectiveTelemetry": {"breakdownCount": 12, "selectedTotalUtility": 1.25, "selectedRiskCost": 0.1},
                        "activeRepair": {"mode": "BOUNDED_ALNS", "runtimeMs": 12, "acceptedMoves": 2, "rejectedMoves": 1, "bestImprovementDelta": 0.25, "frozenPrefixViolationCount": 0, "freshnessImprovementDelta": 0.12, "tailRiskImprovementDelta": 0.08},
                        "tokenUsageSummary": {"totalTokens": 0},
                        "routeVectorMetrics": {"geometryCoverage": 0.0},
                    }),
                    encoding="utf-8",
                )
                (output_dir / f"{stem}.md").write_text("# result", encoding="utf-8")
                return type("Completed", (), {"returncode": 0})()

            original_run_cell = benchmark_runner.run_cell
            try:
                benchmark_runner.run_cell = lambda cell, output_dir, runner=None, run_deferred_xl=False: fake_runner(None)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = benchmark_runner.main(["--scenario-pack", "normal-clear", "--size", "S", "--output-dir", str(output_dir)])
            finally:
                benchmark_runner.run_cell = original_run_cell

            self.assertEqual(0, exit_code)
            summary = (output_dir / "dispatch-quality-summary.md")
            self.assertTrue(summary.is_file())
            summary_text = summary.read_text(encoding="utf-8")
            self.assertIn("bundle candidates retained: `12 -> 8`", summary_text)
            self.assertIn("bundle family diversity count: `3`", summary_text)
            self.assertIn("selector mode: `CP_SAT_TIMEOUT_INCUMBENT`", summary_text)
            self.assertIn("selector pool input/reduced/rejected: `12 / 8 / 4`", summary_text)
            self.assertIn("selector max pool/cap/loss: `256 / True / 0.0`", summary_text)
            self.assertIn("objective breakdown count: `12`", summary_text)
            self.assertIn("objective selected total utility: `1.25`", summary_text)
            self.assertIn("repair mode: `BOUNDED_ALNS`", summary_text)
            self.assertIn("repair frozen prefix violations: `0`", summary_text)
            self.assertIn("repair freshness improvement delta: `0.12`", summary_text)
            self.assertIn("repair accepted/rejected moves: `2 / 1`", summary_text)

    def test_runner_updates_summary_after_each_completed_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            calls = {"count": 0}

            def fake_run_cell(cell, output_dir_arg, runner=None, run_deferred_xl=False):
                calls["count"] += 1
                stem = f"dispatch-quality-{cell.scenario_pack}-{cell.size.lower()}-{cell.execution_mode}-a-20260418-00000{calls['count']}"
                (output_dir_arg / f"{stem}.json").write_text(
                    json.dumps({
                        "baselineId": "A",
                        "scenarioPack": cell.scenario_pack,
                        "workloadSize": cell.size,
                        "decisionMode": cell.decision_mode,
                        "promptFamily": cell.prompt_family,
                        "authoritativeStages": [],
                        "executionMode": cell.execution_mode,
                        "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                        "authorityEligible": False,
                        "metrics": {"selectedProposalCount": 1, "executedAssignmentCount": 1, "robustUtilityAverage": 0.5},
                        "decisionAgreement": {"overallExactMatchRate": 0.0},
                        "tokenUsageSummary": {"totalTokens": 0},
                        "routeVectorMetrics": {"geometryCoverage": 0.0},
                    }),
                    encoding="utf-8",
                )
                (output_dir_arg / f"{stem}.md").write_text("# result", encoding="utf-8")
                return type("Completed", (), {"returncode": 0})()

            original_run_cell = benchmark_runner.run_cell
            try:
                benchmark_runner.run_cell = fake_run_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = benchmark_runner.main([
                        "--scenario-pack", "all",
                        "--size", "S",
                        "--execution-mode", "controlled",
                        "--baseline", "A",
                        "--output-dir", str(output_dir),
                    ])
            finally:
                benchmark_runner.run_cell = original_run_cell

            output = stdout.getvalue()
            self.assertEqual(0, exit_code)
            self.assertEqual(len(benchmark_runner.SCENARIO_PACKS), calls["count"])
            self.assertIn("[CELL ARTIFACT WRITTEN]", output)
            self.assertIn("[CELL ARTIFACT PATHS]", output)
            self.assertIn("[CELL SUMMARY UPDATED]", output)
            self.assertTrue((output_dir / "dispatch-quality-summary.md").is_file())

    def test_run_cell_passes_prompt_family_to_environment(self) -> None:
        cell = benchmark_runner.BenchmarkCell(
            baselines="C",
            size="S",
            scenario_pack="normal-clear",
            decision_mode="legacy",
            prompt_family="v3",
            authoritative_stages=(),
            execution_mode="controlled",
            authority=False,
            profile="dispatch-v2-full-adaptive",
        )
        captured = {}

        def fake_runner(command, cwd=None, text=None, check=None, env=None):
            captured["command"] = command
            captured["env"] = env
            return type("Completed", (), {"returncode": 0})()

        benchmark_runner.run_cell(cell, Path("."), runner=fake_runner)
        self.assertTrue(any(str(arg).startswith("-PbuildDir=") for arg in captured["command"]))
        self.assertEqual("v3", captured["env"]["DISPATCH_QUALITY_PROMPT_FAMILY"])
        self.assertEqual("dispatch-v2-full-adaptive", captured["env"]["DISPATCH_QUALITY_PROFILE"])

    def test_runner_fails_when_completed_cell_writes_no_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run_cell(cell, output_dir_arg, runner=None, run_deferred_xl=False):
                return type("Completed", (), {"returncode": 0})()

            original_run_cell = benchmark_runner.run_cell
            try:
                benchmark_runner.run_cell = fake_run_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = benchmark_runner.main([
                        "--scenario-pack", "normal-clear",
                        "--size", "S",
                        "--baseline", "A",
                        "--output-dir", str(output_dir),
                    ])
            finally:
                benchmark_runner.run_cell = original_run_cell

            output = stdout.getvalue()
            self.assertEqual(1, exit_code)
            self.assertIn("completed without new JSON artifacts", output)


if __name__ == "__main__":
    unittest.main()
