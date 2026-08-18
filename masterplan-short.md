# DX Spotter — Master Plan (Short)

One-page orientation for the DX Spotter project.

## Constitution

Rules governing how work on this project gets done:

- **Verify → Build → Test → Commit.** Never write UI for a server-side
  feature before confirming the server command works (diagnostic tool first).
- Every command given to the user must be copy-paste runnable on *their*
  actual platform/shell (Windows/macOS/Linux) — no mixed comment+command
  lines, no unstated tool-install assumptions.
- One concern per commit (cosmetic / functional / infrastructure), even
  across multi-feature sessions.
- State what's unverified explicitly, in commit messages and code — never
  present aspirational behavior as working.
- Every new external-server interaction needs a one-line runnable diagnostic
  test before it's considered done.

## Spec

- Cross-platform desktop app (Win/macOS/Linux): Python 3.13, tkinter,
  matplotlib. One DX cluster via telnet, CW-only (server-enforced).
- Band scope: static frequency strip (no time axis), center ± BW,
  1/5/10/30-min window, alpha-fade aging, click-to-copy callsign.
- Layout: vertical bandmap — RBN/cluster lane left (tick + label), POTA lane
  right (plain text) — with Band/Bandwidth/Window controls embedded in the
  main window, not a separate filter popup.
- Filtering: server-side via CC Cluster `SET/FILTER` — country, US state,
  band. Dedup: suppress same call+band within N min (cluster spots only).
- POTA lane: public API (`api.pota.app`, no auth), CW-only, filtered to the
  scope's live window, independent right-edge lane (no tick/leader, no
  color distinction, no dedup), own thread/queue, 60s poll.
- Settings persist to `~/.config/spotter/config.json`.
- Out of scope: multi-cluster, ADIF/contest/log upload, a database, audio
  alerts, awards tracking, POTA/RBN spot correlation, KX3 CAT (deferred).

## Plan

- Concurrency: Tk main loop + 2 daemon worker threads (`ClusterConnection`,
  `PotaConnection`), each with its own `queue.Queue`, drained by
  `main.py`'s `after(200)` poll. Only cluster spots pass through
  `DedupCache`.
- Spot store: `BandScope._spots` keyed `(dx_call, band, feed)` — one entry
  per station per feed, so cluster and POTA never evict each other.
  Two independent render lanes, same navy color/fade curve, each with its
  own `_declutter_y()` pass. Decluttering must clip/constrain placement to
  the visible frequency window (ylim) — compress spacing or drop overflow
  rather than letting labels render outside the plotted frame.
- Modules: `main.py` (UI/poll loop) · `cluster.py` (telnet, parser, `Spot`)
  · `pota_client.py` (API worker) · `bandscope.py` (scope widget) ·
  `filter_panel.py` · `filters.py` (dedup, DXCC lookup) · `config.py` ·
  `scope_utils.py`.
- Known loose ends: no `requirements.txt`; POTA status indicator is set
  once at startup, doesn't reflect live health; `main.py` wiring has no
  automated test (manual smoke-test only); backoff timing unasserted.

## Tasks

| Stage | Status |
|---|---|
| 1 — Cluster connection & parser | ✅ complete |
| 2 — Filter engine & config | ✅ complete |
| 3 — UI (3A–3F) | ✅ complete |
| 3G — KX3 CAT integration | deferred |
| 4 — POTA spot integration (4A–4E) | ✅ complete, 65/65 tests pass |
