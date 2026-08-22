"""Visual regression safety net for the bandmap widget.

Two complementary checks, since they catch different classes of bug:

1. TestAxisTickAlignment - a precise, portable invariant check via
   matplotlib's own transform pipeline (no image involved). This is the
   generalized form of the actual bug found and fixed in this project
   (ax2's view drifting from ax after a frequency change, first caught by
   eye as misaligned ticks): for every tick value, the left axis (ax) and
   mirrored right axis (ax2) must land at the same pixel row. Runs across
   several center/bandwidth combinations, not just the default.

2. TestGoldenImage - a full-scene snapshot compared against a stored
   baseline PNG (tests/golden/bandmap_baseline.png), for catching broader
   *unintended* rendering drift as the UI changes (layout shifts, color
   changes, spacing changes) that the narrow tick-alignment check above
   wouldn't notice. When a UI change is intentional, regenerate the
   baseline deliberately:

       UPDATE_GOLDEN=1 py -m unittest tests.test_visual_regression -v

   then review tests/golden/bandmap_baseline.png and commit it.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.image as mpimg
import numpy as np

from bandmap import BandMap
from cluster import Spot

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_DIR.mkdir(exist_ok=True)
BASELINE_PATH = GOLDEN_DIR / "bandmap_baseline.png"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"

# Mean per-pixel difference (0-1 scale, RGBA) tolerated before flagging
# drift. Loose enough to survive minor font-hinting/AA differences across
# machines, tight enough to catch a real layout/color/spacing change.
GOLDEN_MEAN_DIFF_TOLERANCE = 0.01


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except tk.TclError:
        return False


TK_AVAILABLE = _tk_available()


def _fixed_spot(dx_call, freq_khz, feed, spotter="W6YX-#"):
    return Spot(
        dx_call=dx_call,
        spotter=spotter,
        freq_khz=freq_khz,
        band="20m",
        mode="CW",
        comment="",
        time_utc="1637Z",
        feed=feed,
    )


# A fixed, deterministic scene: both lanes populated, spanning most of a
# 50 kHz window, so the golden image actually exercises decluttering.
_SCENE_SPOTS = [
    _fixed_spot("JA1ABC", 14010.0, "DXCLUSTER"),
    _fixed_spot("VK2XYZ", 14015.0, "DXCLUSTER", spotter="N6TV-#"),
    _fixed_spot("G4ABC", 14015.2, "DXCLUSTER", spotter="AK6RI-1-#"),
    _fixed_spot("9A1XYZ", 14030.0, "DXCLUSTER", spotter="K6FOD-#"),
    _fixed_spot("DL1XYZ", 14040.0, "POTA"),
    _fixed_spot("OZ1ABC", 14045.0, "POTA"),
]


@unittest.skipUnless(TK_AVAILABLE, "no display available for Tk widget test")
class TestAxisTickAlignment(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_ticks_aligned_across_window_settings(self):
        # Covers different bands/centers/bandwidths, not just the app's
        # default - the original bug only showed up after a Set-button
        # frequency change, i.e. a non-default window.
        cases = [
            (14025.0, 50.0),
            (14050.0, 50.0),
            (7025.0, 100.0),
            (21025.0, 20.0),
            (28025.0, 80.0),
        ]
        for center_khz, bandwidth_khz in cases:
            with self.subTest(center_khz=center_khz, bandwidth_khz=bandwidth_khz):
                bandmap = BandMap(
                    self.root,
                    center_khz=center_khz,
                    bandwidth_khz=bandwidth_khz,
                    window_minutes=10,
                )
                ax, ax2 = bandmap._ax, bandmap._ax2

                self.assertEqual(
                    ax.get_ylim(), ax2.get_ylim(),
                    "ax2 view has drifted from ax - the exact bug class "
                    "this test exists to catch",
                )

                for tick_val in ax.get_yticks():
                    y_left = ax.transData.transform((0, tick_val))[1]
                    y_right = ax2.transData.transform((0, tick_val))[1]
                    self.assertAlmostEqual(
                        y_left, y_right, delta=1.0,
                        msg=f"tick {tick_val} misaligned by "
                            f"{abs(y_left - y_right):.2f}px between "
                            f"left/right axes",
                    )
                bandmap.destroy()


@unittest.skipUnless(TK_AVAILABLE, "no display available for Tk widget test")
class TestGoldenImage(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_rendering_matches_baseline(self):
        bandmap = BandMap(
            self.root, center_khz=14025.0, bandwidth_khz=50.0, window_minutes=10
        )
        bandmap.add_spots(_SCENE_SPOTS)
        # Fixed size regardless of the (withdrawn, unsized) Tk window's
        # actual geometry at test time - keeps this deterministic across
        # machines/display-scaling instead of depending on Tk layout timing.
        bandmap._fig.set_size_inches(2.66, 6)

        if UPDATE_GOLDEN or not BASELINE_PATH.exists():
            bandmap._fig.savefig(BASELINE_PATH, dpi=100)
            bandmap.destroy()
            self.skipTest(
                f"Wrote baseline to {BASELINE_PATH} (UPDATE_GOLDEN="
                f"{UPDATE_GOLDEN}). Review the image, then commit it."
            )

        actual_path = GOLDEN_DIR / "_actual.png"
        bandmap._fig.savefig(actual_path, dpi=100)
        bandmap.destroy()

        actual = mpimg.imread(actual_path)
        baseline = mpimg.imread(BASELINE_PATH)

        self.assertEqual(
            actual.shape, baseline.shape,
            "canvas dimensions changed - if intentional, regenerate the "
            "baseline with UPDATE_GOLDEN=1",
        )
        diff = np.abs(actual.astype(float) - baseline.astype(float))
        mean_diff = float(diff.mean())
        self.assertLess(
            mean_diff, GOLDEN_MEAN_DIFF_TOLERANCE,
            f"rendering drifted from baseline (mean pixel diff "
            f"{mean_diff:.4f}, tolerance {GOLDEN_MEAN_DIFF_TOLERANCE}). "
            f"If this change is intentional, review {actual_path}, then "
            f"regenerate with UPDATE_GOLDEN=1 and commit the new baseline.",
        )
        actual_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
