import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_ablation.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_ablation", MODULE_PATH)
ablation_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ablation_runner)


class RunDispatchAblationTest(unittest.TestCase):
    def test_dry_run_prints_planned_matrix(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = ablation_runner.main(["--component", "tabular", "--scenario-pack", "normal-clear", "--size", "S", "--dry-run"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("[MATRIX]", output)
        self.assertIn("component=tabular", output)

    def test_dense_bundle_scenario_is_supported_for_focused_greedrl_loop(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = ablation_runner.main([
                "--component", "greedrl",
                "--scenario-pack", "dense-bundle-20x5",
                "--size", "S",
                "--dry-run",
            ])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("component=greedrl", output)
        self.assertIn("scenario-pack=dense-bundle-20x5", output)

    def test_runner_collects_json_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_runner(command, cwd=None, text=None, check=None, env=None):
                (output_dir / "dispatch-quality-ablation-tabular-normal-clear-s-20260418-000000.json").write_text(
                    json.dumps({
                        "toggledComponent": "tabular",
                        "scenarioPack": "normal-clear",
                        "workloadSize": "S",
                        "executionMode": "controlled",
                        "deltaSummary": ["robustUtilityAverage delta=-0.2"],
                    }),
                    encoding="utf-8",
                )
                return type("Completed", (), {"returncode": 0})()

            original_run_cell = ablation_runner.run_cell
            try:
                ablation_runner.run_cell = lambda cell, output_dir, runner=None, run_deferred_xl=False: fake_runner(None)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = ablation_runner.main(["--component", "tabular", "--scenario-pack", "normal-clear", "--size", "S", "--output-dir", str(output_dir)])
            finally:
                ablation_runner.run_cell = original_run_cell

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "dispatch-ablation-summary.md").is_file())


if __name__ == "__main__":
    unittest.main()
