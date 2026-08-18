"""Small pure helpers used by the bandmap and main poll loop."""
from __future__ import annotations

import queue


def format_freq(freq_khz: float) -> str:
    """14025.0 -> '14025.0', 7025.5 -> '7025.5'."""
    return f"{freq_khz:.1f}"


def drain_queue(q: "queue.Queue") -> list:
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items
