import queue
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cluster import (
    ClusterConnection,
    Spot,
    band_filter_commands,
    detect_band,
    detect_mode,
    mode_disable_commands,
    parse_spot,
    spotter_tier_filter_commands,
)


class TestParseSpot(unittest.TestCase):
    def test_standard_spot(self):
        line = "DX de W6YX-3:     14025.0  JA1ABC       CW 22 dB           1637Z"
        spot = parse_spot(line)
        self.assertIsInstance(spot, Spot)
        self.assertEqual(spot.spotter, "W6YX-3")
        self.assertEqual(spot.dx_call, "JA1ABC")
        self.assertEqual(spot.freq_khz, 14025.0)
        self.assertEqual(spot.band, "20m")
        self.assertEqual(spot.mode, "CW")
        self.assertEqual(spot.time_utc, "1637Z")

    def test_comment_captured(self):
        line = "DX de N6TV:        7025.5  DL1XYZ       CW 15 dB some note  0512Z"
        spot = parse_spot(line)
        self.assertIn("CW 15 dB", spot.comment)

    def test_banner_text(self):
        self.assertIsNone(parse_spot("Cluster: 326 nodes  0 Locals  6202 Total users"))

    def test_blank_line(self):
        self.assertIsNone(parse_spot(""))

    def test_non_spot_text(self):
        self.assertIsNone(parse_spot("N6YU de VE7CC-1 18-Aug-2026 1637Z   CCC >"))


class TestDetectBand(unittest.TestCase):
    def test_20m(self):
        self.assertEqual(detect_band(14025.0), "20m")

    def test_40m(self):
        self.assertEqual(detect_band(7025.0), "40m")

    def test_80m(self):
        self.assertEqual(detect_band(3525.0), "80m")

    def test_out_of_band(self):
        self.assertIsNone(detect_band(12345.0))

    def test_boundary_low(self):
        self.assertEqual(detect_band(14000.0), "20m")

    def test_boundary_high(self):
        self.assertEqual(detect_band(14350.0), "20m")


class TestDetectMode(unittest.TestCase):
    def test_cw(self):
        self.assertEqual(detect_mode("CW 22 dB"), "CW")

    def test_ft8(self):
        self.assertEqual(detect_mode("FT8 -10 dB"), "FT8")

    def test_ft4(self):
        self.assertEqual(detect_mode("FT4 spot"), "FT4")

    def test_rtty(self):
        self.assertEqual(detect_mode("RTTY 45 baud"), "RTTY")

    def test_ssb(self):
        self.assertEqual(detect_mode("SSB QSO"), "SSB")

    def test_usb(self):
        self.assertEqual(detect_mode("USB net"), "SSB")

    def test_unknown(self):
        self.assertEqual(detect_mode("some random text"), "UNKNOWN")


class TestModeDisableCommands(unittest.TestCase):
    def test_empty_wanted_disables_all(self):
        cmds = mode_disable_commands([])
        self.assertIn("SET/NOFT8", cmds)
        self.assertIn("SET/NOFT4", cmds)
        self.assertIn("SET/NOCW", cmds)
        self.assertIn("SET/NORTTY", cmds)

    def test_cw_only_disables_other_modes(self):
        cmds = mode_disable_commands(["CW"])
        self.assertNotIn("SET/NOCW", cmds)
        self.assertIn("SET/NOFT8", cmds)
        self.assertIn("SET/NOFT4", cmds)
        self.assertIn("SET/NORTTY", cmds)

    def test_no_nossb_command_exists(self):
        cmds = mode_disable_commands([])
        self.assertNotIn("SET/NOSSB", cmds)


class TestBandFilterCommands(unittest.TestCase):
    def test_rejects_all_but_selected(self):
        cmds = band_filter_commands("20m")
        self.assertEqual(len(cmds), 1)
        self.assertTrue(cmds[0].startswith("SET/FILTER DXBM/REJECT "))
        self.assertNotIn("20,", cmds[0] + ",")

    def test_unknown_band_raises(self):
        with self.assertRaises(ValueError):
            band_filter_commands("11m")


class TestSpotterTierFilterCommands(unittest.TestCase):
    def test_local_passes_only_ca(self):
        cmds = spotter_tier_filter_commands("local")
        self.assertIn("SET/FILTER DOC/PASS K", cmds)
        self.assertIn("SET/FILTER DOS/PASS CA", cmds)

    def test_regional_passes_all_five_states(self):
        cmds = spotter_tier_filter_commands("regional")
        dos_cmd = next(c for c in cmds if c.startswith("SET/FILTER DOS/PASS"))
        for state in ("CA", "AZ", "UT", "ID", "WA"):
            self.assertIn(state, dos_cmd)

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            spotter_tier_filter_commands("national")


class TestAsyncFilterDispatch(unittest.TestCase):
    """Regression: set_band()/set_spotter_tier() are called from the Tk UI
    thread in main.py. _send_filter_setup() blocks ~0.3s per command (7+
    commands); calling it inline froze the whole UI for ~2-4s per click,
    which read as a crash. Both methods must return near-instantly,
    dispatching the actual sends to a background thread instead."""

    def test_set_band_returns_immediately(self):
        conn = ClusterConnection(
            "ve7cc.net", 23, "N6YU", queue.Queue(), selected_band="20m"
        )
        start = time.monotonic()
        conn.set_band("40m")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.5)

    def test_set_spotter_tier_returns_immediately(self):
        conn = ClusterConnection(
            "ve7cc.net", 23, "N6YU", queue.Queue(), selected_tier="local"
        )
        start = time.monotonic()
        conn.set_spotter_tier("regional")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.5)


if __name__ == "__main__":
    unittest.main()
