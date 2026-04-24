import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "probe_llm_provider_responses.py"
SPEC = importlib.util.spec_from_file_location("probe_llm_provider_responses", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


OK_BODY = json.dumps({
    "output": [
        {"content": [{"text": json.dumps({"ok": True})}]}
    ],
    "usage": {"input_tokens": 1, "output_tokens": 1},
})


class LlmProviderResponsesProbeTest(unittest.TestCase):
    def test_classifies_model_unresolved_and_5xx(self) -> None:
        self.assertEqual("provider-model-unresolved", probe.classify_http_failure(404, '{"error":"model not found"}'))
        self.assertEqual("provider-http-5xx", probe.classify_http_failure(503, '{"error":"upstream"}'))
        self.assertEqual("provider-rate-limited", probe.classify_http_failure(429, '{"error":"slow"}'))
        self.assertEqual("provider-auth-error", probe.classify_http_failure(401, '{"error":"bad key"}'))

    def test_probe_accepts_valid_responses_schema(self) -> None:
        def sender(url, api_key, timeout, payload):
            self.assertEqual("https://provider.example/v1/responses", url)
            self.assertEqual("cx/gpt-5.5", payload["model"])
            return 200, OK_BODY

        result = probe.probe_model("https://provider.example/v1", "key", "cx/gpt-5.5", 1.0, sender)

        self.assertTrue(result.accepted)
        self.assertEqual("accepted", result.failure_class)
        self.assertTrue(result.schema_valid)

    def test_run_probe_stops_after_first_accepted_model(self) -> None:
        calls = []

        def fake_probe_model(base_url, api_key, model, timeout_seconds):
            calls.append(model)
            return probe.ProbeResult(model, True, "accepted", 200, 1, True, "hash", "")

        original = probe.probe_model
        try:
            probe.probe_model = fake_probe_model
            payload = probe.run_probe("https://provider.example/v1", "key", ["cx/gpt-5.5", "cx/gpt-5.4"], 1.0)
        finally:
            probe.probe_model = original

        self.assertTrue(payload["ready"])
        self.assertEqual("cx/gpt-5.5", payload["selectedModel"])
        self.assertEqual(["cx/gpt-5.5"], calls)

    def test_main_writes_not_ready_artifacts_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv = Path(temp_dir) / "missing.env"
            output_dir = Path(temp_dir) / "out"
            exit_code = probe.main([
                "--api-key-env", "INTELLIGENTROUTEX_TEST_MISSING_KEY",
                "--dotenv", str(dotenv),
                "--output-dir", str(output_dir),
                "--model", "cx/gpt-5.5",
            ])

            self.assertEqual(1, exit_code)
            reports = list(output_dir.glob("responses_probe-*.json"))
            self.assertEqual(1, len(reports))
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertFalse(payload["ready"])
            self.assertEqual("provider-auth-error", payload["results"][0]["failureClass"])
            self.assertTrue((output_dir / "responses_probe_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
