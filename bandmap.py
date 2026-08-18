"""Vertical bandmap widget: frequency on the Y axis, RBN/cluster spots
(tick + label) on the left, POTA spots (plain text) on the right.

Same visual design as Spotter/bandscope.py (alpha-fade-by-age, isotonic-
regression label decluttering, click-to-copy nearest spot) but a fresh
implementation - the axis orientation and lane layout were confirmed
against that widget's actual behavior via research, not copied from it.
"""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from cluster import Spot

_FADE_FLOOR = 0.3
_TICK_START = 0.02
_TICK_END = 0.10
_LABEL_X = _TICK_END + 0.06
_POTA_TEXT_X = 0.97
_REPAINT_MS = 5000
_ROW_HEIGHT_PX = 14
_LEADER_EPSILON_KHZ = 1e-6


def fade_alpha(age_seconds: float, window_minutes: float) -> float:
    """1.0 when fresh, decaying linearly to _FADE_FLOOR at the window edge."""
    if window_minutes <= 0:
        return _FADE_FLOOR
    age_frac = age_seconds / (window_minutes * 60)
    return max(_FADE_FLOOR, 1.0 - age_frac * (1.0 - _FADE_FLOOR))


def _isotonic_nondecreasing(y: list[float]) -> list[float]:
    """Pool-adjacent-violators: least-squares non-decreasing fit to y."""
    n = len(y)
    if n == 0:
        return []
    values: list[float] = []
    weights: list[float] = []
    starts: list[int] = []
    for i in range(n):
        values.append(y[i])
        weights.append(1.0)
        starts.append(i)
        while len(values) > 1 and values[-2] > values[-1]:
            w = weights[-2] + weights[-1]
            v = (values[-2] * weights[-2] + values[-1] * weights[-1]) / w
            values.pop()
            weights.pop()
            starts.pop()
            values[-1] = v
            weights[-1] = w
    result = [0.0] * n
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else n
        for i in range(start, end):
            result[i] = values[k]
    return result


def _declutter_y(natural_ys: list[float], row_height: float) -> list[float]:
    """Place labels so consecutive ones (by natural position) are at least
    row_height apart, minimizing total squared displacement - isotonic
    regression on y_i - i*row_height, per label lane."""
    if not natural_ys:
        return []
    if row_height <= 0:
        return list(natural_ys)
    order = sorted(range(len(natural_ys)), key=lambda i: natural_ys[i])
    shifted = [natural_ys[order[i]] - i * row_height for i in range(len(order))]
    fitted = _isotonic_nondecreasing(shifted)
    placed_sorted = [fitted[i] + i * row_height for i in range(len(order))]
    result = [0.0] * len(natural_ys)
    for rank, orig_index in enumerate(order):
        result[orig_index] = placed_sorted[rank]
    return result


class BandMap(tk.Frame):
    def __init__(
        self,
        master,
        center_khz: float,
        bandwidth_khz: float,
        window_minutes: float,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._center_khz = center_khz
        self._bandwidth_khz = bandwidth_khz
        self._window_minutes = window_minutes
        # (dx_call.upper(), band, feed) -> (monotonic_timestamp, Spot)
        self._spots: dict[tuple[str, str, str], tuple[float, Spot]] = {}
        self._repaint_job: Optional[str] = None

        self._fig = Figure(figsize=(2.66, 6), tight_layout=True)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._canvas.mpl_connect("button_press_event", self._on_click)

        self._redraw()
        self._schedule_repaint()

    def destroy(self) -> None:
        if self._repaint_job is not None:
            self.after_cancel(self._repaint_job)
            self._repaint_job = None
        super().destroy()

    def add_spots(self, spots: list[Spot]) -> None:
        now = time.monotonic()
        for spot in spots:
            key = (spot.dx_call.upper(), spot.band, spot.feed)
            self._spots[key] = (now, spot)
        self._redraw()

    def set_window(
        self,
        center_khz: Optional[float] = None,
        bandwidth_khz: Optional[float] = None,
        window_minutes: Optional[float] = None,
    ) -> None:
        if center_khz is not None:
            self._center_khz = center_khz
        if bandwidth_khz is not None:
            self._bandwidth_khz = bandwidth_khz
        if window_minutes is not None:
            self._window_minutes = window_minutes
        self._redraw()

    def get_window_khz(self) -> tuple[float, float]:
        return (self._center_khz, self._bandwidth_khz)

    def count_by_feed(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, spot in self._spots.values():
            counts[spot.feed] = counts.get(spot.feed, 0) + 1
        return counts

    def _schedule_repaint(self) -> None:
        self._repaint_job = self.after(_REPAINT_MS, self._tick)

    def _tick(self) -> None:
        self._redraw()
        self._schedule_repaint()

    def _prune(self, now: float) -> None:
        cutoff = self._window_minutes * 60
        expired = [k for k, (ts, _) in self._spots.items() if now - ts >= cutoff]
        for k in expired:
            del self._spots[k]

    def _redraw(self) -> None:
        now = time.monotonic()
        self._prune(now)

        ax = self._ax
        ax.clear()
        ax.set_ylabel("Frequency (kHz)")
        lo = self._center_khz - self._bandwidth_khz / 2
        hi = self._center_khz + self._bandwidth_khz / 2
        if hi <= lo:
            hi = lo + 1
        ax.set_ylim(lo, hi)
        ax.set_xlim(0, 1)
        ax.set_xticks([])

        # Draw once (no spots yet) to get a live renderer/transform so pixel
        # row-height can be converted to data (kHz) units for decluttering.
        self._canvas.draw()
        bbox = ax.get_window_extent()
        pixels_per_khz = bbox.height / (hi - lo) if hi > lo else 0.0
        row_height_khz = _ROW_HEIGHT_PX / pixels_per_khz if pixels_per_khz else 0.0

        cluster_items = [
            (ts, s) for (ts, s) in self._spots.values() if s.feed != "POTA"
        ]
        pota_items = [
            (ts, s) for (ts, s) in self._spots.values() if s.feed == "POTA"
        ]

        self._draw_cluster_lane(cluster_items, now, row_height_khz)
        self._draw_pota_lane(pota_items, now, row_height_khz)

        self._canvas.draw()

    def _draw_cluster_lane(self, items, now, row_height_khz) -> None:
        if not items:
            return
        ax = self._ax
        natural_ys = [spot.freq_khz for _, spot in items]
        placed_ys = _declutter_y(natural_ys, row_height_khz)
        for (ts, spot), placed_y in zip(items, placed_ys):
            alpha = fade_alpha(now - ts, self._window_minutes)
            ax.hlines(
                spot.freq_khz,
                _TICK_START,
                _TICK_END,
                colors="navy",
                linewidth=2,
                alpha=0.85 * alpha,
            )
            if abs(placed_y - spot.freq_khz) > _LEADER_EPSILON_KHZ:
                ax.plot(
                    [_TICK_END, _LABEL_X],
                    [spot.freq_khz, placed_y],
                    color="navy",
                    linewidth=0.6,
                    alpha=0.5 * alpha,
                )
            ax.text(
                _LABEL_X,
                placed_y,
                spot.dx_call,
                ha="left",
                va="center",
                fontsize=8,
                color="navy",
                alpha=alpha,
            )

    def _draw_pota_lane(self, items, now, row_height_khz) -> None:
        if not items:
            return
        ax = self._ax
        natural_ys = [spot.freq_khz for _, spot in items]
        placed_ys = _declutter_y(natural_ys, row_height_khz)
        for (ts, spot), placed_y in zip(items, placed_ys):
            alpha = fade_alpha(now - ts, self._window_minutes)
            ax.text(
                _POTA_TEXT_X,
                placed_y,
                spot.dx_call,
                ha="right",
                va="center",
                fontsize=8,
                color="navy",
                alpha=alpha,
            )

    def _on_click(self, event) -> None:
        if event.inaxes != self._ax or event.ydata is None:
            return
        best_spot: Optional[Spot] = None
        best_dist: Optional[float] = None
        for _, spot in self._spots.values():
            dist = abs(event.ydata - spot.freq_khz)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_spot = spot
        if best_spot is None:
            return
        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(best_spot.dx_call)
