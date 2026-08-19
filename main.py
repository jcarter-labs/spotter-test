"""DX Spotter - launch with `py main.py`.

Vertical bandmap: RBN/DX-cluster spots on the left (tick + label), POTA
spots on the right (plain text), Frequency/Bandwidth/Window controls on
the far right. CW-only, server-side band filtering via ve7cc.net CC Cluster.
"""
from __future__ import annotations

import queue
import time
import tkinter as tk

from bandmap import BandMap
from cluster import ClusterConnection, detect_band
from config import Config
from controls import ControlPanel
from filters import DedupCache, spotter_matches_tier
from pota_client import PotaConnection
from scope_utils import drain_queue

POLL_MS = 200
_DOT_CONNECTED = "#0a8a0a"
_DOT_OTHER = "#b00000"


class SpotterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DX Spotter")

        self._config = Config().load()
        self._spotter_tier = self._config.get("spotter_tier", "local")
        self._band = self._config.get("selected_band", "20m")
        self._spot_queue: "queue.Queue" = queue.Queue()
        self._text_queue: "queue.Queue" = queue.Queue()
        self._pota_queue: "queue.Queue" = queue.Queue()
        self._dedup = DedupCache(window_minutes=self._config.get("dedup_minutes", 10))

        self._build_ui()
        self._connect_cluster()
        self._connect_pota()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    def _build_ui(self) -> None:
        # Status packed first (and BOTTOM) so it reserves its space before
        # the bandmap/controls row expands to fill what's left.
        status = tk.Frame(self, padx=4, pady=2)
        status.pack(side=tk.BOTTOM, fill=tk.X)

        cluster_row = tk.Frame(status)
        cluster_row.pack(fill=tk.X, anchor="w")
        self._cluster_dot = tk.Label(
            cluster_row, text="●", fg=_DOT_OTHER, font=("", 9)
        )
        self._cluster_dot.pack(side=tk.LEFT)
        self._cluster_var = tk.StringVar(value="Cluster: connecting")
        tk.Label(cluster_row, textvariable=self._cluster_var, anchor="w").pack(
            side=tk.LEFT
        )

        self._pota_var = tk.StringVar(value="POTA: connecting")
        tk.Label(status, textvariable=self._pota_var, anchor="w").pack(
            fill=tk.X, anchor="w"
        )

        self._shown_var = tk.StringVar(value="Shown: RBN 0 · POTA 0")
        tk.Label(status, textvariable=self._shown_var, anchor="w").pack(
            fill=tk.X, anchor="w"
        )

        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self._bandmap = BandMap(
            container,
            center_khz=self._config.get("center_khz", 14025.0),
            bandwidth_khz=self._config.get("bandwidth_khz", 50.0),
            window_minutes=self._config.get("window_minutes", 10),
        )
        self._bandmap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._controls = ControlPanel(
            container,
            center_khz=self._config.get("center_khz", 14025.0),
            bandwidth_khz=self._config.get("bandwidth_khz", 50.0),
            window_minutes=self._config.get("window_minutes", 10),
            spotter_tier=self._spotter_tier,
            on_change=self._on_controls_changed,
        )
        self._controls.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)

    def _connect_cluster(self) -> None:
        self._conn = ClusterConnection(
            host=self._config.get("host", "ve7cc.net"),
            port=self._config.get("port", 23),
            callsign=self._config.get("callsign", "N6YU"),
            spot_queue=self._spot_queue,
            text_queue=self._text_queue,
            selected_band=self._config.get("selected_band", "20m"),
            selected_tier=self._spotter_tier,
        )
        self._conn.start()

    def _connect_pota(self) -> None:
        self._pota = PotaConnection(self._pota_queue, self._bandmap.get_window_khz)
        self._pota.start()

    def _on_controls_changed(
        self,
        center_khz: float,
        bandwidth_khz: float,
        window_minutes: float,
        spotter_tier: str,
    ) -> None:
        band = detect_band(center_khz)
        if band is None:
            return  # frequency doesn't fall in a known band - ignore
        self._bandmap.set_window(
            center_khz=center_khz,
            bandwidth_khz=bandwidth_khz,
            window_minutes=window_minutes,
        )
        if band != self._band:
            self._conn.set_band(band)
            self._band = band
        if spotter_tier != self._spotter_tier:
            self._conn.set_spotter_tier(spotter_tier)
            self._spotter_tier = spotter_tier
        self._config.set("selected_band", band)
        self._config.set("center_khz", center_khz)
        self._config.set("bandwidth_khz", bandwidth_khz)
        self._config.set("window_minutes", window_minutes)
        self._config.set("spotter_tier", spotter_tier)

    def _poll(self) -> None:
        new_spots = []
        for spot in drain_queue(self._spot_queue):
            if not spotter_matches_tier(spot.spotter, self._spotter_tier):
                continue
            if not self._dedup.is_dup(spot):
                self._dedup.record(spot)
                new_spots.append(spot)

        pota_spots = drain_queue(self._pota_queue)

        combined = new_spots + pota_spots
        if combined:
            self._bandmap.add_spots(combined)

        drain_queue(self._text_queue)  # server text not surfaced in v1

        self._update_status()
        self.after(POLL_MS, self._poll)

    def _update_status(self) -> None:
        conn = self._conn
        pota = self._pota

        self._cluster_dot.config(
            fg=_DOT_CONNECTED if conn.status == "connected" else _DOT_OTHER
        )
        self._cluster_var.set(f"Cluster: {conn.status}")

        if pota.last_poll_monotonic is not None:
            age_s = int(time.monotonic() - pota.last_poll_monotonic)
            self._pota_var.set(f"POTA: last poll {age_s}s ago")
        else:
            self._pota_var.set(f"POTA: {pota.status}")

        shown = self._bandmap.count_by_feed()
        self._shown_var.set(
            f"Shown: RBN {shown.get('DXCLUSTER', 0)} · POTA {shown.get('POTA', 0)}"
        )

    def _on_close(self) -> None:
        self._conn.stop()
        self._pota.stop()
        self._config.save()
        self.destroy()


def main() -> None:
    app = SpotterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
