import unittest
from unittest import mock

from export_dispatch_instance import build_instance
from run_pyvrp_hgs_baseline import run_bridge


class RunPyvrpHgsBaselineTest(unittest.TestCase):
    def test_missing_pyvrp_writes_dependency_missing_without_failure(self) -> None:
        instance = build_instance("normal-clear", "S", "test-trace")
        with mock.patch("run_pyvrp_hgs_baseline.pyvrp_available", return_value=False):
            payload = run_bridge(instance)

        self.assertEqual("dependency-missing", payload["status"])
        self.assertTrue(payload["skipped"])
        self.assertEqual("pyvrp", payload["dependency"])
        self.assertTrue(payload["fallbackFeasible"])


if __name__ == "__main__":
    unittest.main()
