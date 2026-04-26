from __future__ import annotations

import argparse
import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_full_system_e2e.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_full_system_e2e", MODULE_PATH)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


class FullSystemE2ETest(unittest.TestCase):
    def test_matrix_core_maps_missing_scenarios_to_supported_pack(self) -> None:
        cells = runner.matrix_cells("preset:core", ["full-system"])
        scenarios = [cell.scenario for cell in cells]
        self.assertIn("forecast-heavy", scenarios)
        self.assertIn("dense-bundle-20x5", scenarios)

    def test_parse_modes_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            runner.parse_modes("full-system,bad-mode")

    def test_no_heavy_ml_mode_disables_heavy_workers(self) -> None:
        cell = runner.BenchmarkCell("normal-clear", "S", "no-heavy-ml")
        args = argparse.Namespace(
            prompt_family="v3",
            profile="dispatch-v2-full-adaptive",
            llm_model="cx/gpt-5.5",
            llm_base_url="http://provider/v1",
            routing_provider="osrm",
        )

        env = runner.mode_env(cell, args, Path("out"))

        self.assertEqual("false", env["ROUTECHAIN_DISPATCH_V2_ML_ROUTEFINDER_ENABLED"])
        self.assertEqual("false", env["ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_ENABLED"])
        self.assertEqual("false", env["ROUTECHAIN_DISPATCH_V2_ML_FORECAST_ENABLED"])
        properties = runner.no_heavy_ml_system_properties(cell)
        self.assertIn("-Droutechain.dispatch-v2.ml.routefinder.enabled=false", properties)
        self.assertIn("-Droutechain.dispatch-v2.ml.greedrl.enabled=false", properties)
        self.assertIn("-Droutechain.dispatch-v2.ml.forecast.enabled=false", properties)

    def test_benchmark_cell_artifact_path_includes_size(self) -> None:
        cell = runner.BenchmarkCell("normal-clear", "M", "full-system")
        args = argparse.Namespace(
            prompt_family="v3",
            profile="dispatch-v2-full-adaptive",
            llm_model="cx/gpt-5.5",
            llm_base_url="http://provider/v1",
            routing_provider="osrm",
            cell_timeout="1s",
        )
        original_popen = runner.subprocess.Popen
        try:
            class FakeProcess:
                pid = 12345

                def wait(self, timeout=None):
                    return 0

            runner.subprocess.Popen = lambda *a, **k: FakeProcess()
            row = runner.run_benchmark_cell(cell, args, Path("root"))
        finally:
            runner.subprocess.Popen = original_popen

        self.assertTrue(row["artifactRoot"].endswith("mode-comparison\\full-system\\normal-clear\\M") or row["artifactRoot"].endswith("mode-comparison/full-system/normal-clear/M"))

    def test_benchmark_cell_timeout_returns_fail_reason(self) -> None:
        cell = runner.BenchmarkCell("normal-clear", "S", "full-system")
        args = argparse.Namespace(
            prompt_family="v3",
            profile="dispatch-v2-full-adaptive",
            llm_model="cx/gpt-5.5",
            llm_base_url="http://provider/v1",
            routing_provider="osrm",
            cell_timeout="1s",
        )
        original_popen = runner.subprocess.Popen
        original_terminate = runner.terminate_process_tree
        try:
            terminated = []

            class TimeoutProcess:
                pid = 54321

                def wait(self, timeout=None):
                    raise runner.subprocess.TimeoutExpired("gradle", timeout or 1)

            runner.subprocess.Popen = lambda *a, **k: TimeoutProcess()
            runner.terminate_process_tree = lambda process_id: terminated.append(process_id)
            row = runner.run_benchmark_cell(cell, args, Path("root"))
        finally:
            runner.subprocess.Popen = original_popen
            runner.terminate_process_tree = original_terminate

        self.assertEqual("FAIL", row["verdict"])
        self.assertIn("benchmark-cell-timeout", row["reasons"])
        self.assertEqual([54321], terminated)

    def test_osrm_ready_from_route_probe_when_health_missing(self) -> None:
        calls = []
        original = runner.http_get
        try:
            def fake_get(url, timeout_seconds=5.0):
                calls.append(url)
                if url.endswith("/health"):
                    return runner.HttpResult(False, 404, 1, "", "not found")
                return runner.HttpResult(True, 200, 1, '{"code":"Ok"}')
            runner.http_get = fake_get
            result = runner.check_osrm("http://127.0.0.1:5000")
        finally:
            runner.http_get = original
        self.assertTrue(result["ready"])
        self.assertEqual("Ok", result["routeProbe"]["code"])

    def test_llm_fallback_records_second_model(self) -> None:
        original = runner.http_post_json
        try:
            def fake_post(url, payload, headers, timeout_seconds=20.0):
                self.assertEqual("json_schema", payload["text"]["format"]["type"])
                if payload["model"] == "cx/gpt-5.5":
                    return runner.HttpResult(False, 404, 1, "", "missing")
                return runner.HttpResult(True, 200, 1, '{"id":"resp_1","output":[]}')
            runner.http_post_json = fake_post
            env_key = "IRX_TEST_LLM_KEY"
            import os
            os.environ[env_key] = "test"
            result = runner.check_llm("http://provider/v1", ("cx/gpt-5.5", "cx/gpt-5.4"), env_key)
        finally:
            runner.http_post_json = original
        self.assertTrue(result["ready"])
        self.assertEqual("cx/gpt-5.4", result["modelUsed"])
        self.assertTrue(result["modelResolutionFallbackUsed"])

    def test_preflight_blocks_when_workers_are_not_attached(self) -> None:
        original_workers = runner.check_workers
        original_osrm = runner.check_osrm
        original_llm = runner.check_llm
        try:
            runner.check_workers = lambda: {"ready": False, "workers": []}
            runner.check_osrm = lambda base_url: {"ready": True}
            runner.check_llm = lambda base_url, models, api_key_env: {"ready": True}
            args = argparse.Namespace(llm="on", llm_base_url="http://provider/v1", llm_model="cx/gpt-5.5", llm_fallback_model="cx/gpt-5.4", llm_api_key_env="KEY")
            result = runner.run_preflight(args)
        finally:
            runner.check_workers = original_workers
            runner.check_osrm = original_osrm
            runner.check_llm = original_llm
        self.assertEqual("LOCAL_ML_NOT_ATTACHED", result["verdict"])


if __name__ == "__main__":
    unittest.main()



