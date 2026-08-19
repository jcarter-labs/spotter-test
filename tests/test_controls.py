import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controls import ControlPanel


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except tk.TclError:
        return False


TK_AVAILABLE = _tk_available()


@unittest.skipUnless(TK_AVAILABLE, "no display available for Tk widget test")
class TestControlPanel(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.calls = []
        self.panel = ControlPanel(
            self.root,
            center_khz=14025.0,
            bandwidth_khz=50.0,
            window_minutes=10,
            spotter_tier="local",
            on_change=lambda *args: self.calls.append(args),
        )

    def tearDown(self):
        self.root.destroy()

    def test_initial_freq_var_shown_in_mhz(self):
        self.assertEqual(self.panel._freq_var.get(), "14.025")

    def test_set_converts_mhz_to_khz(self):
        self.panel._freq_var.set("21.025")
        self.panel._changed()
        self.assertEqual(len(self.calls), 1)
        center_khz, bandwidth_khz, window_minutes, spotter_tier = self.calls[0]
        self.assertAlmostEqual(center_khz, 21025.0)
        self.assertEqual(bandwidth_khz, 50.0)
        self.assertEqual(window_minutes, 10.0)
        self.assertEqual(spotter_tier, "local")

    def test_invalid_frequency_does_not_call_on_change(self):
        self.panel._freq_var.set("not-a-number")
        self.panel._changed()
        self.assertEqual(self.calls, [])

    def test_bandwidth_options_include_40_and_80(self):
        from controls import BANDWIDTH_OPTIONS_KHZ

        self.assertIn(40, BANDWIDTH_OPTIONS_KHZ)
        self.assertIn(80, BANDWIDTH_OPTIONS_KHZ)

    def test_changing_tier_reflected_in_callback(self):
        self.panel._tier_var.set("regional")
        self.panel._changed()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][3], "regional")


if __name__ == "__main__":
    unittest.main()
