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
        result = _declutter_y([100.0, 200.0, 300.0], row_height=1.0, lo=0.0, hi=1000.0)
        self.assertEqual(result, [100.0, 200.0, 300.0])

    def test_overlapping_labels_spread_apart(self):
        result = _declutter_y([100.0, 100.1, 100.2], row_height=1.0, lo=0.0, hi=1000.0)
        ordered = sorted(result)
        for a, b in zip(ordered, ordered[1:]):
            self.assertGreaterEqual(b - a, 1.0 - 1e-9)

    def test_zero_row_height_returns_natural(self):
        result = _declutter_y([5.0, 1.0], row_height=0, lo=0.0, hi=10.0)
        self.assertEqual(result, [5.0, 1.0])

    def test_empty(self):
        self.assertEqual(_declutter_y([], row_height=1.0, lo=0.0, hi=10.0), [])

    def test_never_escapes_window_when_overcrowded(self):
        # 50 labels wanting 1 kHz of row each, but only a 10 kHz-wide window
        # - far more demand than fits. Every placed position must stay
        # inside [lo, hi] rather than spilling past the frame.
        natural = [float(i) for i in range(50)]
        result = _declutter_y(natural, row_height=1.0, lo=0.0, hi=10.0)
        self.assertEqual(len(result), 50)
        for p in result:
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 10.0)

    def test_overcrowded_preserves_relative_order(self):
        natural = [5.0, 1.0, 3.0]
        result = _declutter_y(natural, row_height=100.0, lo=0.0, hi=10.0)
        self.assertLess(result[1], result[2])  # 1.0 < 3.0
        self.assertLess(result[2], result[0])  # 3.0 < 5.0

    def test_single_item_outside_window_gets_clamped(self):
        result = _declutter_y([9999.0], row_height=1.0, lo=0.0, hi=10.0)
        self.assertEqual(result, [10.0])

    def test_tight_cluster_does_not_drag_in_separated_points(self):
        # Regression: 6 points crammed within 0.6 kHz near the bottom, plus
        # 5 points already comfortably spread out (8 kHz apart, well over
        # row_height) higher up. Total demand (10 kHz) fits easily in the
        # 50 kHz window, so nothing here should need compression - but the
        # old pre-shrink-row_height approach forced them all into one PAVA
        # pool, flinging one label (the last of the tight cluster) up near
        # the top while its true neighbors stayed at the bottom.
        natural = [
            14000.1, 14000.2, 14000.3, 14000.4, 14000.5, 14000.6,
            14008.0, 14016.0, 14022.0, 14030.0, 14040.0,
        ]
        result = _declutter_y(natural, row_height=1.0, lo=14000.0, hi=14050.0)
        # The tight cluster (first 6) must stay tight - no member should
        # land more than a few kHz from its natural position.
        for natural_y, placed_y in zip(natural[:6], result[:6]):
            self.assertLess(abs(placed_y - natural_y), 10.0)
        # And the whole result must stay ordered and within the window.
        self.assertEqual(result, sorted(result))
        for p in result:
            self.assertGreaterEqual(p, 14000.0)
            self.assertLessEqual(p, 14050.0)


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

    def test_count_by_feed_excludes_out_of_window_spots(self):
        # Regression: a spot can be on-band (server-side filter passes it,
        # e.g. anywhere in 20m) but far outside this particular slice of
        # it - it must not count as "shown" nor be handed to decluttering.
        bandmap = BandMap(self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10)
        bandmap.add_spots(
            [
                self._spot("N6OVP", 14047.1, "DXCLUSTER"),  # in window
                self._spot("HI5PPH", 14270.0, "DXCLUSTER"),  # on-band, off-window
            ]
        )
        self.assertEqual(len(bandmap._spots), 2)  # both stored
        self.assertEqual(bandmap.count_by_feed(), {"DXCLUSTER": 1})  # only 1 shown
        bandmap.destroy()

    def test_ax2_stays_in_sync_with_ax_after_window_change(self):
        # Regression: ax2.set_yticks(ax.get_yticks()) auto-expands ax2's
        # view to fit every tick value, including the locator's out-of-
        # range padding candidates (e.g. a 14025-14075 view's ticks include
        # 14020 and 14080) - silently overriding ax2's set_ylim(). ax2 must
        # stay clamped to exactly the same range as ax.
        bandmap = BandMap(self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10)
        bandmap.set_window(center_khz=14050.0, bandwidth_khz=50.0, window_minutes=10)
        self.assertEqual(bandmap._ax.get_ylim(), bandmap._ax2.get_ylim())
        bandmap.destroy()


if __name__ == "__main__":
    unittest.main()
