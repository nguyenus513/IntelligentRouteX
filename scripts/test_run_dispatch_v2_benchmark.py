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
                        "llmShadowAgreement": {"overallExactMatchRate": 0.0},
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
            self.assertTrue((output_dir / "dispatch-quality-summary.md").is_file())

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
                        "llmShadowAgreement": {"overallExactMatchRate": 0.0},
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
            self.assertEqual(6, calls["count"])
            self.assertIn("[CELL ARTIFACT WRITTEN]", output)
            self.assertIn("[CELL SUMMARY UPDATED]", output)
            self.assertTrue((output_dir / "dispatch-quality-summary.md").is_file())

    def test_run_cell_passes_prompt_family_to_environment(self) -> None:
        cell = benchmark_runner.BenchmarkCell(
            baselines="C",
            size="S",
            scenario_pack="normal-clear",
            decision_mode="llm-shadow",
            prompt_family="v3",
            authoritative_stages=(),
            execution_mode="controlled",
            authority=False,
            profile="dispatch-v2-full-adaptive",
        )
        captured = {}

        def fake_runner(command, cwd=None, text=None, check=None, env=None):
            captured["env"] = env
            return type("Completed", (), {"returncode": 0})()

        benchmark_runner.run_cell(cell, Path("."), runner=fake_runner)
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
