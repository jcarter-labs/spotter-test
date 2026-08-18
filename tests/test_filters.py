import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cluster import Spot
from filters import DedupCache


def make_spot(dx_call="JA1ABC", band="20m"):
    return Spot(
        dx_call=dx_call,
        spotter="W6YX-3",
        freq_khz=14025.0,
        band=band,
        mode="CW",
        comment="",
        time_utc="1637Z",
    )


class TestDedupCache(unittest.TestCase):
    def test_first_spot_not_dup(self):
        cache = DedupCache(window_minutes=10)
        self.assertFalse(cache.is_dup(make_spot()))

    def test_second_spot_suppressed(self):
        cache = DedupCache(window_minutes=10)
        spot = make_spot()
        cache.record(spot)
        self.assertTrue(cache.is_dup(spot))

    def test_different_band_not_suppressed(self):
        cache = DedupCache(window_minutes=10)
        cache.record(make_spot(band="20m"))
        self.assertFalse(cache.is_dup(make_spot(band="40m")))

    def test_case_insensitive_call(self):
        cache = DedupCache(window_minutes=10)
        cache.record(make_spot(dx_call="ja1abc"))
        self.assertTrue(cache.is_dup(make_spot(dx_call="JA1ABC")))

    def test_passes_after_window_expires(self):
        cache = DedupCache(window_minutes=0.0001)  # ~6ms
        spot = make_spot()
        cache.record(spot)
        time.sleep(0.05)
        self.assertFalse(cache.is_dup(spot))

    def test_sweep_evicts_expired_keys(self):
        cache = DedupCache(window_minutes=0.0001, sweep_every=2)
        cache.record(make_spot(dx_call="AAA"))
        time.sleep(0.05)
        cache.record(make_spot(dx_call="BBB"))
        self.assertEqual(len(cache._seen), 1)


if __name__ == "__main__":
    unittest.main()
