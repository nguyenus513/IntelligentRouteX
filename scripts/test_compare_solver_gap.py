import unittest

from compare_solver_gap import compare, pct_gap


class CompareSolverGapTest(unittest.TestCase):
    def test_gap_metrics_are_zero_safe(self) -> None:
        self.assertEqual(0.0, pct_gap(10, 0))
        report = compare(
            {"solver": "current", "vehicleCount": 2, "totalDistanceMeters": 100, "totalDurationSeconds": 50, "servedOrderCount": 8, "feasible": True, "runtimeMs": 12},
            {"solver": "baseline", "vehicleCount": 1, "totalDistanceMeters": 0, "totalDurationSeconds": 0, "servedOrderCount": 8, "feasible": True, "runtimeMs": 10},
        )

        self.assertEqual("solver-gap-report/v1", report["schemaVersion"])
        self.assertEqual(1, report["vehicle_count_gap"])
        self.assertIn("strong_baseline_gap", report)
        self.assertEqual(0.0, report["distance_gap_pct"])


if __name__ == "__main__":
    unittest.main()
