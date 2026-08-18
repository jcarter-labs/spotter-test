"""Dedup cache for cluster/RBN spots. POTA spots bypass this entirely."""
from __future__ import annotations

import time

from cluster import Spot


class DedupCache:
    """Suppresses re-spots of the same (call, band) within window_minutes.

    Unlike the design this is inspired by, expired keys are swept
    periodically rather than left to accumulate for the process lifetime -
    a long contest session would otherwise grow this dict unboundedly.
    """

    def __init__(self, window_minutes: float = 10, sweep_every: int = 500):
        self._window_s = window_minutes * 60
        self._seen: dict[tuple[str, str], float] = {}
        self._sweep_every = sweep_every
        self._calls_since_sweep = 0

    def is_dup(self, spot: Spot) -> bool:
        key = (spot.dx_call.upper(), spot.band)
        last = self._seen.get(key)
        if last is None:
            return False
        return (time.monotonic() - last) < self._window_s

    def record(self, spot: Spot) -> None:
        key = (spot.dx_call.upper(), spot.band)
        self._seen[key] = time.monotonic()
        self._calls_since_sweep += 1
        if self._calls_since_sweep >= self._sweep_every:
            self._sweep()

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [k for k, ts in self._seen.items() if now - ts >= self._window_s]
        for k in expired:
            del self._seen[k]
        self._calls_since_sweep = 0
