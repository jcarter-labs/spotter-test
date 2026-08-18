import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bandmap import BandMap, _declutter_y, _isotonic_nondecreasing, fade_alpha
from cluster import Spot


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except tk.TclError:
        return False


TK_AVAILABLE = _tk_available()


class TestFadeAlpha(unittest.TestCase):
    def test_fresh_spot_full_alpha(self):
        self.assertEqual(fade_alpha(0, window_minutes=10), 1.0)

    def test_at_window_edge_hits_floor(self):
        self.assertAlmostEqual(fade_alpha(600, window_minutes=10), 0.3)

    def test_never_below_floor(self):
        self.assertEqual(fade_alpha(10_000, window_minutes=10), 0.3)

    def test_halfway_is_between(self):
        alpha = fade_alpha(300, window_minutes=10)
        self.assertGreater(alpha, 0.3)
        self.assertLess(alpha, 1.0)


class TestIsotonicNondecreasing(unittest.TestCase):
    def test_already_nondecreasing_unchanged(self):
        self.assertEqual(_isotonic_nondecreasing([1, 2, 3]), [1, 2, 3])

    def test_decreasing_pair_averaged(self):
        result = _isotonic_nondecreasing([2, 1])
        self.assertEqual(result, [1.5, 1.5])

    def test_empty(self):
        self.assertEqual(_isotonic_nondecreasing([]), [])

    def test_result_is_nondecreasing(self):
        result = _isotonic_nondecreasing([5, 1, 4, 2, 3])
        self.assertEqual(result, sorted(result))


class TestDeclutterY(unittest.TestCase):
    def test_widely_spaced_labels_unchanged(self):
        result = _declutter_y([100.0, 200.0, 300.0], row_height=1.0)
        self.assertEqual(result, [100.0, 200.0, 300.0])

    def test_overlapping_labels_spread_apart(self):
        result = _declutter_y([100.0, 100.1, 100.2], row_height=1.0)
        ordered = sorted(result)
        for a, b in zip(ordered, ordered[1:]):
            self.assertGreaterEqual(b - a, 1.0 - 1e-9)

    def test_zero_row_height_returns_natural(self):
        self.assertEqual(_declutter_y([5.0, 1.0], row_height=0), [5.0, 1.0])

    def test_empty(self):
        self.assertEqual(_declutter_y([], row_height=1.0), [])


@unittest.skipUnless(TK_AVAILABLE, "no display available for Tk widget test")
class TestBandMapStorage(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def _spot(self, dx_call, freq_khz, feed):
        return Spot(
            dx_call=dx_call,
            spotter="W6YX-3",
            freq_khz=freq_khz,
            band="20m",
            mode="CW",
            comment="",
            time_utc="1637Z",
            feed=feed,
        )

    def test_same_call_band_different_feed_both_stored(self):
        bandmap = BandMap(self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10)
        bandmap.add_spots(
            [
                self._spot("JA1ABC", 14025.0, "DXCLUSTER"),
                self._spot("JA1ABC", 14025.0, "POTA"),
            ]
        )
        self.assertEqual(len(bandmap._spots), 2)
        bandmap.destroy()

    def test_respot_same_feed_updates_not_duplicates(self):
        bandmap = BandMap(self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10)
        bandmap.add_spots([self._spot("JA1ABC", 14025.0, "DXCLUSTER")])
        bandmap.add_spots([self._spot("JA1ABC", 14026.0, "DXCLUSTER")])
        self.assertEqual(len(bandmap._spots), 1)
        bandmap.destroy()

    def test_get_window_khz(self):
        bandmap = BandMap(self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10)
        self.assertEqual(bandmap.get_window_khz(), (14025.0, 50.0))
        bandmap.destroy()


if __name__ == "__main__":
    unittest.main()
