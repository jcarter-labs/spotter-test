"""Telnet connection to a CC Cluster (ve7cc.net) DX cluster node.

Login sequence, mode/band filter commands, and spot-line parsing were derived
by cross-checking Spotter/spotter_master_plan.md's verified/failed command
tables against Spotter/cluster.py's live-tested behavior. This is a fresh
implementation, not a copy.
"""
from __future__ import annotations

import dataclasses
import queue
import re
import socket
import threading
import time
from typing import Optional

CONNECT_TIMEOUT_S = 30.0
LOGIN_WAIT_S = 2.0
SKIMMER_WAIT_S = 0.5
FILTER_CMD_WAIT_S = 0.3
BACKOFF_START_S = 5.0
BACKOFF_CAP_S = 60.0

# (band, low_khz, high_khz) - inclusive bounds, first match wins.
BAND_RANGES = [
    ("160m", 1800, 2000),
    ("80m", 3500, 4000),
    ("60m", 5330, 5410),
    ("40m", 7000, 7300),
    ("30m", 10100, 10150),
    ("20m", 14000, 14350),
    ("17m", 18068, 18168),
    ("15m", 21000, 21450),
    ("12m", 24890, 24990),
    ("10m", 28000, 29700),
    ("6m", 50000, 54000),
]

ALL_BANDS = [name for name, _, _ in BAND_RANGES]

_SPOT_RE = re.compile(r"DX de (\S+?):\s+([\d.]+)\s+(\S+)\s+(.*)\s+(\d{4}Z)")

# Checked in this order; first substring match in the comment text wins.
_MODE_KEYWORDS = [
    ("FT8", "FT8"),
    ("FT4", "FT4"),
    ("RTTY", "RTTY"),
    ("CW", "CW"),
    ("SSB", "SSB"),
    ("USB", "SSB"),
    ("LSB", "SSB"),
]

# Confirmed working on ve7cc.net (Spotter/spotter_master_plan.md). SET/NOSSB
# is NOT included here - confirmed invalid ("command error") on this node.
_MODE_DISABLE_CMDS = {
    "FT8": "SET/NOFT8",
    "FT4": "SET/NOFT4",
    "CW": "SET/NOCW",
    "RTTY": "SET/NORTTY",
}


def detect_band(freq_khz: float) -> Optional[str]:
    for name, low, high in BAND_RANGES:
        if low <= freq_khz <= high:
            return name
    return None


def detect_mode(comment: str) -> str:
    upper = comment.upper()
    for keyword, mode in _MODE_KEYWORDS:
        if keyword in upper:
            return mode
    return "UNKNOWN"


def mode_disable_commands(wanted_modes: list[str]) -> list[str]:
    """Commands to disable every mode NOT in wanted_modes."""
    return [
        cmd
        for mode, cmd in _MODE_DISABLE_CMDS.items()
        if mode not in wanted_modes
    ]


def band_filter_commands(selected_band: str) -> list[str]:
    """Reject every band except selected_band, CC Cluster DXBM/REJECT syntax."""
    if selected_band not in ALL_BANDS:
        raise ValueError(f"unknown band: {selected_band!r}")
    reject = [b[:-1] for b in ALL_BANDS if b != selected_band]
    return [f"SET/FILTER DXBM/REJECT {','.join(reject)}"]


# Vetted spotter tiers, from Radio/Projects/spot_filt/nc7j_spotter_groups.md.
# "regional" is a superset of "local" (matches spot_filter.py's own tiering).
# CC Cluster has no exact spotter-callsign filter (SET/SPOTTER, SET/ORIGIN
# are both confirmed invalid) - DOC/DOS (country/state) is the finest
# server-side granularity available, so this is a coarse pre-filter only.
# Exact matching happens client-side (see filters.spotter_matches_tier).
SPOTTER_TIER_CALLS: dict[str, frozenset[str]] = {
    "local": frozenset({"W6YX", "AK6RI-1", "N6TV"}),
    "regional": frozenset(
        {
            "W6YX", "AK6RI-1", "N6TV",
            "K6FOD", "WA7LNW", "ND7K", "K7CO", "NG7M",
            "N7VVX", "N7TUG", "KD7EFG", "KW7MM", "KW7MM-2",
        }
    ),
}

# States derived from each tier's spotters' QRZ/grid locations - all in CA
# for local; regional adds AZ (KW7MM, KW7MM-2), UT (KD7EFG, NG7M), ID
# (K7CO, N7VVX), WA (N7TUG). Confirmed via QRZ lookup for the three that
# had no grid on record (KD7EFG, KW7MM, KW7MM-2).
SPOTTER_TIER_STATES: dict[str, list[str]] = {
    "local": ["CA"],
    "regional": ["CA", "AZ", "UT", "ID", "WA"],
}


def spotter_tier_filter_commands(tier: str) -> list[str]:
    """Coarse server-side pre-filter for a spotter tier: US spotters in the
    tier's states. Narrows traffic only - does not replace exact matching."""
    if tier not in SPOTTER_TIER_STATES:
        raise ValueError(f"unknown spotter tier: {tier!r}")
    states = ",".join(SPOTTER_TIER_STATES[tier])
    return [
        "SET/FILTER DOC/PASS K",
        f"SET/FILTER DOS/PASS {states}",
    ]


@dataclasses.dataclass
class Spot:
    dx_call: str
    spotter: str
    freq_khz: float
    band: str
    mode: str
    comment: str
    time_utc: str
    feed: str = "DXCLUSTER"


def parse_spot(line: str) -> Optional[Spot]:
    match = _SPOT_RE.match(line.strip())
    if not match:
        return None
    spotter, freq_str, dx_call, comment, time_utc = match.groups()
    freq_khz = float(freq_str)
    return Spot(
        dx_call=dx_call,
        spotter=spotter,
        freq_khz=freq_khz,
        band=detect_band(freq_khz) or "UNKNOWN",
        mode=detect_mode(comment),
        comment=comment,
        time_utc=time_utc,
    )


class ClusterConnection:
    """Telnet worker thread. Parsed spots go to spot_queue; everything else
    (banners, SH/FILTER echoes, etc.) goes to text_queue if given."""

    def __init__(
        self,
        host: str,
        port: int,
        callsign: str,
        spot_queue: "queue.Queue[Spot]",
        text_queue: "Optional[queue.Queue[str]]" = None,
        selected_band: str = "20m",
        selected_tier: str = "local",
    ):
        self._host = host
        self._port = port
        self._callsign = callsign
        self._spot_queue = spot_queue
        self._text_queue = text_queue
        self._selected_band = selected_band
        self._selected_tier = selected_tier
        self._stop_event = threading.Event()
        self._sock_lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

        # Diagnostics - best-effort, read-only from the UI thread. Not
        # lock-protected: single-writer (worker thread), and stale-by-one-
        # tick reads are fine for a status display.
        self.status = "disconnected"  # disconnected | connecting | connected
        self.connect_count = 0
        self.reconnect_count = 0
        self.last_connected_monotonic: Optional[float] = None
        self.received_count = 0
        self.offband_count = 0  # parsed spots whose band != selected_band

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._sock_lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def set_band(self, band: str) -> None:
        self._selected_band = band
        self.received_count = 0
        self.offband_count = 0
        self._send_filter_setup_async()

    def set_spotter_tier(self, tier: str) -> None:
        self._selected_tier = tier
        self._send_filter_setup_async()

    def _send_filter_setup_async(self) -> None:
        """set_band()/set_spotter_tier() are called from the Tk UI thread.
        _send_filter_setup() blocks for ~2s (FILTER_CMD_WAIT_S between each
        of ~7 commands) - running it inline froze the whole UI for the
        duration. Dispatch it to a short-lived background thread instead;
        send_command() is already lock-protected per-command, so concurrent
        setup calls (e.g. rapid clicks) can interleave commands safely."""
        threading.Thread(target=self._send_filter_setup, daemon=True).start()

    def send_command(self, cmd: str) -> None:
        with self._sock_lock:
            sock = self._sock
        if sock is None:
            return
        try:
            sock.sendall((cmd + "\r\n").encode())
        except OSError:
            pass

    def _send_filter_setup(self) -> None:
        commands = ["UNSET/FILTER"]
        commands.extend(mode_disable_commands(["CW"]))
        commands.extend(band_filter_commands(self._selected_band))
        commands.extend(spotter_tier_filter_commands(self._selected_tier))
        for cmd in commands:
            self.send_command(cmd)
            self._stop_event.wait(FILTER_CMD_WAIT_S)

    def _run(self) -> None:
        backoff = BACKOFF_START_S
        while not self._stop_event.is_set():
            self.status = "connecting"
            self.connect_count += 1
            if self.connect_count > 1:
                self.reconnect_count += 1
            try:
                self._connect_and_read()
                backoff = BACKOFF_START_S
            except OSError:
                pass
            self.status = "disconnected"
            if self._stop_event.is_set():
                break
            self._stop_event.wait(backoff)
            backoff = min(backoff * 2, BACKOFF_CAP_S)

    def _connect_and_read(self) -> None:
        sock = socket.create_connection(
            (self._host, self._port), timeout=CONNECT_TIMEOUT_S
        )
        sock.settimeout(None)
        with self._sock_lock:
            self._sock = sock
        try:
            sock.sendall((self._callsign + "\r\n").encode())
            self._stop_event.wait(LOGIN_WAIT_S)
            sock.sendall(b"SET/SKIMMER\r\n")
            self._stop_event.wait(SKIMMER_WAIT_S)
            self._send_filter_setup()
            self.status = "connected"
            self.last_connected_monotonic = time.monotonic()

            fh = sock.makefile("r", errors="replace")
            for line in fh:
                if self._stop_event.is_set():
                    break
                spot = parse_spot(line)
                if spot is not None:
                    self.received_count += 1
                    if spot.band != self._selected_band:
                        self.offband_count += 1
                    try:
                        self._spot_queue.put_nowait(spot)
                    except queue.Full:
                        pass
                else:
                    text = line.rstrip()
                    if text and self._text_queue is not None:
                        try:
                            self._text_queue.put_nowait(text)
                        except queue.Full:
                            pass
        finally:
            with self._sock_lock:
                self._sock = None
            try:
                sock.close()
            except OSError:
                pass
