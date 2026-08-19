import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bandmap import BandMap
from config import Config
from main import SpotterApp


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except tk.TclError:
        return False


TK_AVAILABLE = _tk_available()


class FakeConn:
    def __init__(self):
        self.calls = []

    def set_band(self, band):
        self.calls.append(("set_band", band))

    def set_spotter_tier(self, tier):
        self.calls.append(("set_spotter_tier", tier))


@unittest.skipUnless(TK_AVAILABLE, "no display available for Tk widget test")
class TestOnControlsChanged(unittest.TestCase):
    """Regression: a tier-only change was calling both set_band() (always,
    unconditionally) and set_spotter_tier() - each dispatches a ~2s filter
    setup - doubling the work needlessly and, before the async-dispatch fix,
    freezing the UI for ~4s on every tier click (perceived as a crash)."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = SpotterApp.__new__(SpotterApp)
        self.app._bandmap = BandMap(
            self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10
        )
        self.app._conn = FakeConn()
        self.app._config = Config()
        self.app._config.data = {}
        self.app._spotter_tier = "local"
        self.app._band = "20m"

    def tearDown(self):
        self.root.destroy()

    def test_tier_only_change_does_not_resend_band(self):
        self.app._on_controls_changed(
            center_khz=14025.0,
            bandwidth_khz=50.0,
            window_minutes=10.0,
            spotter_tier="regional",
        )
        self.assertEqual(self.app._conn.calls, [("set_spotter_tier", "regional")])

    def test_band_only_change_does_not_resend_tier(self):
        self.app._on_controls_changed(
            center_khz=7025.0,
            bandwidth_khz=50.0,
            window_minutes=10.0,
            spotter_tier="local",
        )
        self.assertEqual(self.app._conn.calls, [("set_band", "40m")])

    def test_no_change_sends_nothing(self):
        self.app._on_controls_changed(
            center_khz=14025.0,
            bandwidth_khz=50.0,
            window_minutes=10.0,
            spotter_tier="local",
        )
        self.assertEqual(self.app._conn.calls, [])

    def test_both_changed_sends_both_exactly_once(self):
        self.app._on_controls_changed(
            center_khz=7025.0,
            bandwidth_khz=50.0,
            window_minutes=10.0,
            spotter_tier="regional",
        )
        self.assertEqual(
            self.app._conn.calls,
            [("set_band", "40m"), ("set_spotter_tier", "regional")],
        )

    def test_does_not_raise(self):
        try:
            self.app._on_controls_changed(
                center_khz=21025.0,
                bandwidth_khz=50.0,
                window_minutes=10.0,
                spotter_tier="regional",
            )
        except Exception as e:  # pragma: no cover - failure path
            self.fail(f"_on_controls_changed raised: {e!r}")


if __name__ == "__main__":
    unittest.main()
