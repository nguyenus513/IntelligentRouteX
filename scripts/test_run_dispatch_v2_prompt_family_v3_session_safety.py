import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_prompt_family_v3_session_safety.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_prompt_family_v3_session_safety", MODULE_PATH)
session_safety_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = session_safety_runner
SPEC.loader.exec_module(session_safety_runner)


def write_junit_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<testsuite name="com.routechain.v2.decision.DecisionSessionStoreSafetyTest" tests="2" failures="0" errors="0" skipped="0">
  <testcase classname="com.routechain.v2.decision.DecisionSessionStoreSafetyTest" name="sameTraceCanReadUpstreamStageRefs" time="0.123"/>
  <testcase classname="com.routechain.v2.decision.DecisionSessionStoreSafetyTest" name="differentTraceCannotReadSessionData" time="0.045"/>
</testsuite>
""",
        encoding="utf-8",
    )


class PromptFamilyV3SessionSafetyRunnerTest(unittest.TestCase):
    def test_dry_run_prints_configuration(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = session_safety_runner.main(["--dry-run"])

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("[SESSION SAFETY] test-class=", output)

    def test_collects_existing_junit_report_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            test_results_dir = temp_root / "build" / "test-results" / "test"
            output_dir = temp_root / "out"
            write_junit_report(test_results_dir / "TEST-com.routechain.v2.decision.DecisionSessionStoreSafetyTest.xml")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = session_safety_runner.main([
                    "--test-results-dir", str(test_results_dir),
                    "--output-dir", str(output_dir),
                ])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "session_safety_report.md").is_file())
            report = (output_dir / "session_safety_report.md").read_text(encoding="utf-8")
            self.assertIn("sameTraceCanReadUpstreamStageRefs", report)
            self.assertIn("differentTraceCannotReadSessionData", report)

    def test_rerun_tests_uses_gradle_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            test_results_dir = temp_root / "build" / "test-results" / "test"
            output_dir = temp_root / "out"
            calls = {"count": 0}

            def fake_run_tests(runner=None):
                calls["count"] += 1
                write_junit_report(test_results_dir / "TEST-com.routechain.v2.decision.DecisionSessionStoreSafetyTest.xml")
                return 0

            original_run_tests = session_safety_runner.run_tests
            try:
                session_safety_runner.run_tests = fake_run_tests
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = session_safety_runner.main([
                        "--rerun-tests",
                        "--test-results-dir", str(test_results_dir),
                        "--output-dir", str(output_dir),
                    ])
            finally:
                session_safety_runner.run_tests = original_run_tests

            self.assertEqual(1, calls["count"])
            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "session_safety_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
