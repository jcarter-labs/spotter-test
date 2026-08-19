"""Dedup cache and spotter-tier matching for cluster/RBN spots. POTA spots
bypass both - this module only applies to the RBN/cluster lane."""
from __future__ import annotations

import time

from cluster import SPOTTER_TIER_CALLS, Spot


def spotter_matches_tier(spotter_call: str, tier: str) -> bool:
    """Exact client-side match against a vetted spotter tier - CC Cluster's
    own DOC/DOS filter is only country/state grained (see
    cluster.spotter_tier_filter_commands), so this is the real gate.

    Matches the base call and any of its -SSID variants, e.g. "AK6RI-1"
    matches "AK6RI-1", "AK6RI-1-2", ... but not "AK6RI-10" or "AK6RI".

    Also matches a literal "-#" suffix: confirmed live against ve7cc.net
    that VE7CC's server marks skimmer-originated spots with a literal hash
    character (e.g. "DX de WA7LNW-#: ..."), not a resolved numeric SSID -
    this is not the AR-Cluster "-#" wildcard syntax, it's what actually
    appears in real spot data on this server."""
    allowed = SPOTTER_TIER_CALLS[tier]
    for base in allowed:
        if spotter_call == base:
            return True
        if spotter_call.startswith(base + "-"):
            suffix = spotter_call[len(base) + 1:]
            if suffix.isdigit() or suffix == "#":
                return True
    return False


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
