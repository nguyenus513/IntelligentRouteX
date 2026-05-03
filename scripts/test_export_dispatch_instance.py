import json
import tempfile
import unittest
from pathlib import Path

import export_dispatch_instance as exporter


class ExportDispatchInstanceTest(unittest.TestCase):
    def test_export_creates_valid_schema_with_orders_drivers_and_square_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "instance.json"
            self.assertEqual(0, exporter.main(["--scenario-pack", "normal-clear", "--size", "S", "--output", str(output)]))
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("dispatch-academic-instance/v1", payload["schemaVersion"])
        self.assertTrue(payload["orders"])
        self.assertTrue(payload["drivers"])
        node_count = len(payload["drivers"]) + len(payload["orders"]) * 2
        self.assertEqual(node_count, len(payload["distanceMatrixMeters"]))
        self.assertTrue(all(len(row) == node_count for row in payload["durationMatrixSeconds"]))


if __name__ == "__main__":
    unittest.main()
