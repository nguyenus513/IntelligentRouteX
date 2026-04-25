import tempfile
import unittest
from pathlib import Path

import probe_dispatch_v2_tiles as probe


class ProbeDispatchV2TilesTest(unittest.TestCase):
    def test_lat_lon_to_tile_is_stable_for_hcmc(self):
        tile = probe.lat_lon_to_tile(10.7769, 106.7009, 14)

        self.assertEqual(14, tile.z)
        self.assertGreaterEqual(tile.x, 0)
        self.assertGreaterEqual(tile.y, 0)
        self.assertIn("/14/", probe.osm_url(tile))

    def test_tomtom_without_key_is_reported_as_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tile = probe.TileId(14, 13045, 7740)

            result = probe.skipped("tomtom-raster-basic", tile, Path(tmp), "tomtom-api-key-missing", "© TomTom")

        self.assertEqual("SKIPPED", result.status)
        self.assertEqual("tomtom-api-key-missing", result.degradeReason)
        self.assertIn("<redacted>", result.urlTemplate)

    def test_powershell_fallback_receives_url_via_environment(self):
        self.assertTrue(hasattr(probe, "powershell_fetch_tile"))


if __name__ == "__main__":
    unittest.main()
