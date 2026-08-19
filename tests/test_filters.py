import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cluster import Spot
from filters import DedupCache, spotter_matches_tier


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


class TestSpotterMatchesTier(unittest.TestCase):
    def test_exact_base_call_matches_local(self):
        self.assertTrue(spotter_matches_tier("W6YX", "local"))

    def test_ssid_variant_matches_local(self):
        self.assertTrue(spotter_matches_tier("W6YX-3", "local"))

    def test_hyphenated_base_call_matches_local(self):
        self.assertTrue(spotter_matches_tier("AK6RI-1", "local"))

    def test_hyphenated_base_call_ssid_variant_matches_local(self):
        self.assertTrue(spotter_matches_tier("AK6RI-1-2", "local"))

    def test_non_local_spotter_rejected_by_local(self):
        self.assertFalse(spotter_matches_tier("K6FOD", "local"))

    def test_regional_includes_local_spotters(self):
        self.assertTrue(spotter_matches_tier("W6YX", "regional"))

    def test_regional_includes_regional_only_spotters(self):
        self.assertTrue(spotter_matches_tier("K6FOD", "regional"))
        self.assertTrue(spotter_matches_tier("KW7MM-2", "regional"))

    def test_unrelated_spotter_rejected_by_regional(self):
        self.assertFalse(spotter_matches_tier("VE7CC", "regional"))

    def test_similar_but_different_call_not_a_false_positive(self):
        # "AK6RI-10" must not match the "AK6RI-1" base via substring luck.
        self.assertFalse(spotter_matches_tier("AK6RI-10", "local"))
        # A bare prefix without the hyphenated "-1" is a different station.
        self.assertFalse(spotter_matches_tier("AK6RI", "local"))

    def test_literal_hash_ssid_matches_local(self):
        # Regression: confirmed live on ve7cc.net via raw byte capture that
        # VE7CC's server marks skimmer-originated spots with a literal "#"
        # character (e.g. "DX de W6YX-#: ..."), not a resolved numeric
        # SSID. This is NOT the AR-Cluster "-#" wildcard filter syntax -
        # it's what actually appears in real CC Cluster spot data. Every
        # real spot from a vetted spotter was being silently rejected
        # before this was accounted for.
        self.assertTrue(spotter_matches_tier("W6YX-#", "local"))

    def test_literal_hash_ssid_matches_regional(self):
        self.assertTrue(spotter_matches_tier("WA7LNW-#", "regional"))
        self.assertTrue(spotter_matches_tier("KW7MM-#", "regional"))

    def test_literal_hash_ssid_on_hyphenated_base(self):
        self.assertTrue(spotter_matches_tier("AK6RI-1-#", "local"))

    def test_literal_hash_ssid_does_not_match_unrelated_call(self):
        self.assertFalse(spotter_matches_tier("SK6AW-#", "regional"))


if __name__ == "__main__":
    unittest.main()
