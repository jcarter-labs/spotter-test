import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from cluster import Spot
from pota_client import (
    PotaConnection,
    fetch_spots,
    filter_to_window,
    normalize_spot,
)


def make_raw(**overrides):
    raw = {
        "activator": "VA3VBE",
        "frequency": "14074.0",
        "mode": "CW",
        "comments": "RBN -14 dB via WA7LNW-#",
        "spotter": "WA7LNW-#",
        "spotTime": "2026-08-18T16:57:26",
        "source": "RBN",
        "expire": 1323,
    }
    raw.update(overrides)
    return raw


class TestNormalizeSpot(unittest.TestCase):
    def test_cw_mode_normalized(self):
        spot = normalize_spot(make_raw())
        self.assertIsInstance(spot, Spot)
        self.assertEqual(spot.dx_call, "VA3VBE")
        self.assertEqual(spot.freq_khz, 14074.0)
        self.assertEqual(spot.feed, "POTA")

    def test_non_cw_mode_dropped(self):
        self.assertIsNone(normalize_spot(make_raw(mode="FT8")))

    def test_empty_mode_dropped(self):
        self.assertIsNone(normalize_spot(make_raw(mode="")))

    def test_lowercase_mode_matched(self):
        spot = normalize_spot(make_raw(mode="cw"))
        self.assertIsNotNone(spot)

    def test_missing_activator_returns_none(self):
        raw = make_raw()
        del raw["activator"]
        self.assertIsNone(normalize_spot(raw))

    def test_blank_activator_returns_none(self):
        self.assertIsNone(normalize_spot(make_raw(activator="")))

    def test_invalid_frequency_returns_none(self):
        self.assertIsNone(normalize_spot(make_raw(frequency="not-a-number")))

    def test_missing_optional_fields_tolerated(self):
        raw = make_raw()
        del raw["spotter"]
        del raw["comments"]
        del raw["spotTime"]
        spot = normalize_spot(raw)
        self.assertEqual(spot.spotter, "")
        self.assertEqual(spot.comment, "")
        self.assertEqual(spot.time_utc, "")

    def test_extra_unknown_fields_ignored(self):
        spot = normalize_spot(make_raw(grid4="EN93", locationDesc="CA-ON"))
        self.assertIsNotNone(spot)

    def test_inconsistent_decimal_formatting_both_parse(self):
        self.assertEqual(normalize_spot(make_raw(frequency="7076")).freq_khz, 7076.0)
        self.assertEqual(normalize_spot(make_raw(frequency="14058.0")).freq_khz, 14058.0)


class TestFilterToWindow(unittest.TestCase):
    def test_spot_inside_window_kept(self):
        spot = normalize_spot(make_raw(frequency="14025.0"))
        result = filter_to_window([spot], center_khz=14025.0, bandwidth_khz=50.0)
        self.assertEqual(result, [spot])

    def test_spot_outside_window_dropped(self):
        spot = normalize_spot(make_raw(frequency="14100.0"))
        result = filter_to_window([spot], center_khz=14025.0, bandwidth_khz=50.0)
        self.assertEqual(result, [])

    def test_spot_at_window_edge_kept(self):
        spot = normalize_spot(make_raw(frequency="14050.0"))
        result = filter_to_window([spot], center_khz=14025.0, bandwidth_khz=50.0)
        self.assertEqual(result, [spot])


class TestFetchSpots(unittest.TestCase):
    @patch("pota_client.requests.get")
    def test_returns_only_cw_spots(self, mock_get):
        mock_get.return_value = Mock(
            json=lambda: [make_raw(), make_raw(activator="W1AW", mode="FT8")],
            raise_for_status=lambda: None,
        )
        spots = fetch_spots()
        self.assertEqual(len(spots), 1)
        self.assertEqual(spots[0].dx_call, "VA3VBE")

    @patch("pota_client.requests.get")
    def test_http_error_propagates(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500")
        mock_get.return_value = mock_response
        with self.assertRaises(requests.HTTPError):
            fetch_spots()

    @patch("pota_client.requests.get")
    def test_malformed_entry_skipped_not_crashed(self, mock_get):
        mock_get.return_value = Mock(
            json=lambda: [make_raw(), {"activator": "BAD"}],
            raise_for_status=lambda: None,
        )
        spots = fetch_spots()
        self.assertEqual(len(spots), 1)


class TestPotaConnectionPolling(unittest.TestCase):
    def test_spots_within_window_queued(self):
        q = queue.Queue()
        conn = PotaConnection(q, window_fn=lambda: (14074.0, 50.0), poll_seconds=0.05)
        with patch("pota_client.fetch_spots", return_value=[normalize_spot(make_raw())]):
            conn.start()
            conn._stop_event.wait(0.2)
            conn.stop()
        self.assertGreaterEqual(q.qsize(), 1)

    def test_spots_outside_window_not_queued(self):
        spots = [normalize_spot(make_raw(frequency="21025.0"))]
        filtered = filter_to_window(spots, 14025.0, 50.0)
        self.assertEqual(filtered, [])

    def test_fetch_failure_does_not_crash_thread(self):
        q = queue.Queue()
        conn = PotaConnection(q, window_fn=lambda: (14025.0, 50.0), poll_seconds=0.05)
        with patch("pota_client.fetch_spots", side_effect=requests.RequestException("boom")):
            conn.start()
            conn._stop_event.wait(0.2)
            conn.stop()
        self.assertEqual(q.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
