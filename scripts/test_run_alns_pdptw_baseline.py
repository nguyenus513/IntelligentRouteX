import unittest

from export_dispatch_instance import build_instance
from run_alns_pdptw_baseline import solve


class RunAlnsPdptwBaselineTest(unittest.TestCase):
    def test_baseline_is_deterministic_and_serves_all_orders(self) -> None:
        instance = build_instance("normal-clear", "S", "test-trace")
        first = solve(instance)
        second = solve(instance)

        self.assertEqual(first["routes"], second["routes"])
        self.assertTrue(first["feasible"])
        self.assertEqual(len(instance["orders"]), first["servedOrderCount"])
        self.assertGreater(first["totalDistanceMeters"], 0)


if __name__ == "__main__":
    unittest.main()
