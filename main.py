"""DX Spotter - launch with `py main.py`.

Vertical bandmap: RBN/DX-cluster spots on the left (tick + label), POTA
spots on the right (plain text), Band/Bandwidth/Window pulldowns on the
far right. CW-only, server-side band filtering via ve7cc.net CC Cluster.
"""
from __future__ import annotations

import queue
import time
import tkinter as tk

from bandmap import BandMap
from cluster import ClusterConnection
from config import Config
from controls import BAND_CENTER_KHZ, ControlPanel
from filters import DedupCache
from pota_client import PotaConnection
from scope_utils import drain_queue

POLL_MS = 200


class SpotterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DX Spotter")

        self._config = Config().load()
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
            selected_band=self._config.get("selected_band", "20m"),
            bandwidth_khz=self._config.get("bandwidth_khz", 50.0),
            window_minutes=self._config.get("window_minutes", 10),
            on_change=self._on_controls_changed,
        )
        self._controls.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)

        self._status_var = tk.StringVar(value="Connecting...")
        tk.Label(self, textvariable=self._status_var, anchor="w").pack(fill=tk.X)

    def _connect_cluster(self) -> None:
        self._conn = ClusterConnection(
            host=self._config.get("host", "ve7cc.net"),
            port=self._config.get("port", 23),
            callsign=self._config.get("callsign", "N6YU"),
            spot_queue=self._spot_queue,
            text_queue=self._text_queue,
            selected_band=self._config.get("selected_band", "20m"),
        )
        self._conn.start()

    def _connect_pota(self) -> None:
        self._pota = PotaConnection(self._pota_queue, self._bandmap.get_window_khz)
        self._pota.start()

    def _on_controls_changed(self, band: str, bandwidth_khz: float, window_minutes: float) -> None:
        center_khz = BAND_CENTER_KHZ.get(band, self._config.get("center_khz", 14025.0))
        self._bandmap.set_window(
            center_khz=center_khz,
            bandwidth_khz=bandwidth_khz,
            window_minutes=window_minutes,
        )
        self._conn.set_band(band)
        self._config.set("selected_band", band)
        self._config.set("center_khz", center_khz)
        self._config.set("bandwidth_khz", bandwidth_khz)
        self._config.set("window_minutes", window_minutes)

    def _poll(self) -> None:
        new_spots = []
        for spot in drain_queue(self._spot_queue):
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

        cluster_bit = f"Cluster: {conn.status}"
        if conn.reconnect_count:
            cluster_bit += f" (reconnects: {conn.reconnect_count})"
        cluster_bit += f" rx={conn.received_count}"
        if conn.offband_count:
            cluster_bit += f" off-band={conn.offband_count}"

        pota_bit = f"POTA: {pota.status}"
        if pota.last_poll_monotonic is not None:
            age_s = int(time.monotonic() - pota.last_poll_monotonic)
            pota_bit += f" last poll {age_s}s ago, fetched={pota.last_fetch_count} in-window={pota.last_queued_count}"

        shown = self._bandmap.count_by_feed()
        shown_bit = f"Shown - RBN: {shown.get('DXCLUSTER', 0)} POTA: {shown.get('POTA', 0)}"

        self._status_var.set(f"{cluster_bit} | {pota_bit} | {shown_bit}")

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
