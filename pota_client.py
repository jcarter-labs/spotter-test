"""Polling client for the public POTA activator-spot API.

Field quirks (frequency is a string with inconsistent decimal formatting,
spotTime has no timezone suffix, expire is unreliable) were confirmed by a
live probe against api.pota.app and cross-checked against
Spotter/spotter_master_plan.md's Stage 4A notes. Fresh implementation.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

import requests

from cluster import Spot, detect_band

POTA_URL = "https://api.pota.app/spot/activator"
REQUEST_TIMEOUT_S = 10
POLL_SECONDS = 60
BACKOFF_START_S = 5.0
BACKOFF_CAP_S = 60.0


def normalize_spot(raw: dict) -> Optional[Spot]:
    try:
        mode = str(raw["mode"]).upper()
        if mode != "CW":
            return None
        freq_khz = float(raw["frequency"])
        dx_call = raw["activator"]
        if not dx_call:
            return None
    except (KeyError, TypeError, ValueError):
        return None

    return Spot(
        dx_call=dx_call,
        spotter=raw.get("spotter") or "",
        freq_khz=freq_khz,
        band=detect_band(freq_khz) or "UNKNOWN",
        mode=mode,
        comment=raw.get("comments") or "",
        time_utc=raw.get("spotTime") or "",
        feed="POTA",
    )


def fetch_spots() -> list[Spot]:
    response = requests.get(POTA_URL, timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    spots = []
    for raw in response.json():
        spot = normalize_spot(raw)
        if spot is not None:
            spots.append(spot)
    return spots


def filter_to_window(spots: list[Spot], center_khz: float, bandwidth_khz: float) -> list[Spot]:
    lo = center_khz - bandwidth_khz / 2
    hi = center_khz + bandwidth_khz / 2
    return [s for s in spots if lo <= s.freq_khz <= hi]


class PotaConnection:
    """Daemon-thread poller. POTA spots bypass dedup - the feed is a live
    snapshot, not an event stream, so re-seeing the same call is expected."""

    def __init__(
        self,
        spot_queue: "queue.Queue[Spot]",
        window_fn: Callable[[], tuple[float, float]],
        poll_seconds: float = POLL_SECONDS,
    ):
        self._spot_queue = spot_queue
        self._window_fn = window_fn
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Diagnostics - best-effort, read-only from the UI thread.
        self.status = "connecting"  # connecting | ok | error
        self.poll_count = 0
        self.last_poll_monotonic: Optional[float] = None
        self.last_fetch_count = 0  # CW spots returned by the API, pre-window-filter
        self.last_queued_count = 0  # of those, how many were inside the live window

    def start(self) -> None:
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _poll_loop(self) -> None:
        backoff = BACKOFF_START_S
        while not self._stop_event.is_set():
            try:
                spots = fetch_spots()
            except requests.RequestException:
                self.status = "error"
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, BACKOFF_CAP_S)
                continue

            backoff = BACKOFF_START_S
            self.status = "ok"
            self.poll_count += 1
            self.last_poll_monotonic = time.monotonic()
            self.last_fetch_count = len(spots)

            center_khz, bandwidth_khz = self._window_fn()
            in_window = filter_to_window(spots, center_khz, bandwidth_khz)
            self.last_queued_count = len(in_window)
            for spot in in_window:
                try:
                    self._spot_queue.put_nowait(spot)
                except queue.Full:
                    pass

            self._stop_event.wait(self._poll_seconds)
