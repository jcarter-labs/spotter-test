"""Right-side control panel: Frequency (MHz) entry + Set, Bandwidth, Window,
Spotter tier.

Embedded directly in the main window rather than a separate popup, per the
requested layout. Frequency is typed directly (MHz) rather than chosen from
a band-name dropdown; the band name needed for the server-side filter is
derived from the typed frequency via cluster.detect_band().
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

BANDWIDTH_OPTIONS_KHZ = [10, 20, 40, 50, 80, 100]
WINDOW_OPTIONS_MIN = [1, 5, 10, 30]
SPOTTER_TIERS = [("Local", "local"), ("Regional", "regional")]


class ControlPanel(tk.Frame):
    def __init__(
        self,
        master,
        center_khz: float,
        bandwidth_khz: float,
        window_minutes: float,
        spotter_tier: str,
        on_change: Callable[[float, float, float, str], None],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_change = on_change

        self._freq_var = tk.StringVar(value=f"{center_khz / 1000:.3f}")
        self._bandwidth_var = tk.StringVar(value=str(int(bandwidth_khz)))
        self._window_var = tk.StringVar(value=str(int(window_minutes)))
        self._tier_var = tk.StringVar(value=spotter_tier)

        tk.Label(self, text="Frequency (MHz)").pack(anchor="w")
        freq_row = tk.Frame(self)
        freq_row.pack(fill=tk.X)
        freq_entry = ttk.Entry(freq_row, textvariable=self._freq_var, width=10)
        freq_entry.pack(side=tk.LEFT)
        freq_entry.bind("<Return>", self._changed)
        ttk.Button(freq_row, text="Set", command=self._changed).pack(
            side=tk.LEFT, padx=(4, 0)
        )

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

        tk.Label(self, text="Spotter").pack(anchor="w", pady=(10, 0))
        for label, value in SPOTTER_TIERS:
            tk.Radiobutton(
                self,
                text=label,
                variable=self._tier_var,
                value=value,
                command=self._changed,
            ).pack(anchor="w")

    def _changed(self, _event=None) -> None:
        try:
            center_khz = float(self._freq_var.get()) * 1000
        except ValueError:
            return
        bandwidth_khz = float(self._bandwidth_var.get())
        window_minutes = float(self._window_var.get())
        spotter_tier = self._tier_var.get()
        self._on_change(center_khz, bandwidth_khz, window_minutes, spotter_tier)
