import unittest

import build_community_gap_report as gap_report


class BuildCommunityGapReportTest(unittest.TestCase):
    def test_summarizes_vehicle_gap_and_operator(self) -> None:
        rows = [
            {"suite": "solomon", "instance": "R101", "problemType": "VRPTW", "vehicleCount": 21, "bestKnownVehicleCount": 19, "vehicleGap": 2, "totalDistance": 1.0, "bestKnownDistance": 1.0, "objectiveGapPercent": 0.1, "feasible": True, "verdict": "PASS_WITH_LIMITS", "verdictReasons": [], "recommendedOperator": gap_report.recommend_operator("VRPTW", 2), "solutionPath": ""},
            {"suite": "li-lim", "instance": "LR101", "problemType": "PDPTW", "vehicleCount": 20, "bestKnownVehicleCount": 19, "vehicleGap": 1, "totalDistance": 1.0, "bestKnownDistance": 1.0, "objectiveGapPercent": 0.2, "feasible": True, "verdict": "PASS_WITH_LIMITS", "verdictReasons": [], "recommendedOperator": gap_report.recommend_operator("PDPTW", 1), "solutionPath": ""},
        ]

        report = gap_report.summarize(rows)

        self.assertFalse(report["pass"])
        self.assertEqual(3, report["vehicleGapSum"])
        self.assertEqual(2, report["gapInstanceCount"])
        self.assertEqual("route-elimination-cross-exchange", rows[0]["recommendedOperator"])
        self.assertEqual("pair-aware-route-elimination-ejection", rows[1]["recommendedOperator"])

    def test_passes_when_all_feasible_and_no_vehicle_gap(self) -> None:
        rows = [{"vehicleGap": 0, "feasible": True, "objectiveGapPercent": 0.0, "instance": "C101"}]

        report = gap_report.summarize(rows)

        self.assertTrue(report["pass"])
        self.assertEqual(0, report["vehicleGapSum"])


if __name__ == "__main__":
    unittest.main()
