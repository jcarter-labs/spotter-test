"""Right-side pulldown control panel: Band, Bandwidth, Window.

Embedded directly in the main window rather than a separate popup, per the
requested layout.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from cluster import ALL_BANDS

# Station has no 160m/80m capability - excluded from the selectable list.
SELECTABLE_BANDS = [b for b in ALL_BANDS if b not in ("160m", "80m")]

BANDWIDTH_OPTIONS_KHZ = [10, 20, 50, 100]
WINDOW_OPTIONS_MIN = [1, 5, 10, 30]

# Typical CW-segment center frequency per band, kHz.
BAND_CENTER_KHZ = {
    "60m": 5357.0,
    "40m": 7025.0,
    "30m": 10110.0,
    "20m": 14025.0,
    "17m": 18080.0,
    "15m": 21025.0,
    "12m": 24900.0,
    "10m": 28025.0,
    "6m": 50100.0,
}


class ControlPanel(tk.Frame):
    def __init__(
        self,
        master,
        selected_band: str,
        bandwidth_khz: float,
        window_minutes: float,
        on_change: Callable[[str, float, float], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_change = on_change

        self._band_var = tk.StringVar(value=selected_band)
        self._bandwidth_var = tk.StringVar(value=str(int(bandwidth_khz)))
        self._window_var = tk.StringVar(value=str(int(window_minutes)))

        tk.Label(self, text="Band").pack(anchor="w")
        band_menu = ttk.Combobox(
            self, textvariable=self._band_var, values=SELECTABLE_BANDS, state="readonly"
        )
        band_menu.pack(fill=tk.X)
        band_menu.bind("<<ComboboxSelected>>", self._changed)

        tk.Label(self, text="Bandwidth (kHz)").pack(anchor="w", pady=(10, 0))
        bw_menu = ttk.Combobox(
            self,
            textvariable=self._bandwidth_var,
            values=[str(v) for v in BANDWIDTH_OPTIONS_KHZ],
            state="readonly",
        )
        bw_menu.pack(fill=tk.X)
        bw_menu.bind("<<ComboboxSelected>>", self._changed)

        tk.Label(self, text="Window (min)").pack(anchor="w", pady=(10, 0))
        window_menu = ttk.Combobox(
            self,
            textvariable=self._window_var,
            values=[str(v) for v in WINDOW_OPTIONS_MIN],
            state="readonly",
        )
        window_menu.pack(fill=tk.X)
        window_menu.bind("<<ComboboxSelected>>", self._changed)

    def _changed(self, _event=None) -> None:
        band = self._band_var.get()
        bandwidth_khz = float(self._bandwidth_var.get())
        window_minutes = float(self._window_var.get())
        self._on_change(band, bandwidth_khz, window_minutes)
