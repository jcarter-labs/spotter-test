"""Live smoke test: is the telnet spot feed actually alive?

Opt-in only - hits the real network, so it's not part of the default
`unittest discover` hygiene the rest of the suite follows. Run explicitly:

    SPOTTER_LIVE_TEST=1 py -m unittest tests.test_live_smoke -v

This deliberately does NOT use our app's narrow spotter-tier filtering
(that has its own tests in test_filters.py/test_cluster.py) - it just
confirms the telnet connection to the DX cluster itself is alive and
producing parseable spots. If this fails, the problem is connectivity or
the cluster, not our filtering logic.
"""
from __future__ import annotations

import os
import socket
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cluster import parse_spot
from config import DEFAULTS

LISTEN_SECONDS = 30
LOGIN_WAIT_S = 2.0
SKIMMER_WAIT_S = 0.5


@unittest.skipUnless(
    os.environ.get("SPOTTER_LIVE_TEST") == "1",
    "live network test - set SPOTTER_LIVE_TEST=1 to run",
)
class TestLiveSpotFeed(unittest.TestCase):
    def test_receives_at_least_one_spot(self):
        host, port, callsign = DEFAULTS["host"], DEFAULTS["port"], DEFAULTS["callsign"]
        sock = socket.create_connection((host, port), timeout=30.0)
        self.addCleanup(sock.close)
        sock.settimeout(None)

        sock.sendall((callsign + "\r\n").encode())
        time.sleep(LOGIN_WAIT_S)
        sock.sendall(b"SET/SKIMMER\r\n")
        time.sleep(SKIMMER_WAIT_S)

        sock.settimeout(LISTEN_SECONDS + 5)
        fh = sock.makefile("r", errors="replace")
        spot_count = 0
        start = time.monotonic()
        try:
            for line in fh:
                if parse_spot(line) is not None:
                    spot_count += 1
                if time.monotonic() - start > LISTEN_SECONDS:
                    break
        except (socket.timeout, OSError):
            pass

        self.assertGreater(
            spot_count,
            0,
            f"received zero parseable spots from {host}:{port} in "
            f"{LISTEN_SECONDS}s - telnet connection or cluster may be down, "
            f"not a filtering issue (this test bypasses our spotter-tier "
            f"filters entirely)",
        )


if __name__ == "__main__":
    unittest.main()
