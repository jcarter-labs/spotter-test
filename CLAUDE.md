# CLAUDE.md — Spotter-test

## Environment

This project runs on Windows, no venv. Bare `python`/`python3` resolve to
non-functional Microsoft Store stubs (they just open the Store) — **always
use the `py` launcher**, which resolves correctly to a real interpreter.

Shell state does not persist between tool calls — never rely on `cd` or an
activation step carrying over; use absolute paths or repeat `cd` per call.

At the start of a session (or if anything environment-related seems off),
run:

```
py scripts/doctor.py
```

It checks Python resolution, required packages (`matplotlib`, `requests`),
PowerShell execution policy, and reachability of the DX cluster
(`ve7cc.net:23`). On success it writes `scripts/env.json` with the resolved
absolute interpreter path (`python_exe`) — read that file if you need the
exact path rather than re-deriving it. `scripts/env.json` is gitignored
(machine-specific).

## Testing

```
py -m unittest discover -v tests/
```

Fast, offline, ~100 tests. One test is excluded by default:
`tests/test_live_smoke.py` hits the real DX cluster telnet feed and is
opt-in only:

```
SPOTTER_LIVE_TEST=1 py -m unittest tests.test_live_smoke -v
```

It asserts we receive at least one parseable spot within 30s, deliberately
bypassing this app's own spotter-tier filtering (that logic has its own
tests in `test_filters.py`/`test_cluster.py`) — if this one fails, the
telnet connection or the cluster itself is the problem, not our filters.

## Visual regression safety net

`tests/test_visual_regression.py` has two checks, run as part of the
normal suite above (not opt-in, no network):

- `TestAxisTickAlignment` — a precise, portable check via matplotlib's own
  transform pipeline (no image involved) that the left axis (`ax`) and
  mirrored right axis (`ax2`) land on the same pixel row for every tick,
  across several center/bandwidth combinations. This is the generalized
  form of a real bug this project hit: `ax2`'s view silently drifting
  from `ax` after a frequency change, first caught by eye as visibly
  misaligned ticks (see `masterplan-short.md`).
- `TestGoldenImage` — a full-scene snapshot compared against
  `tests/golden/bandmap_baseline.png`, for catching broader *unintended*
  rendering drift (layout shifts, spacing, color) as the UI changes.

When you make an **intentional** UI change and this test fails, don't
treat that as a bug - regenerate the baseline, review it, commit it:

```
UPDATE_GOLDEN=1 py -m unittest tests.test_visual_regression -v
```

Then open `tests/golden/bandmap_baseline.png` and actually look at it
before committing - this workflow only stays useful if someone looks at
the image every time it changes, not just re-runs the command.

## Process cleanup on Windows

`kill` from the Bash tool does not reliably map to the real Windows PID
here — a background Python/Tk process can survive it. Verify with
`tasklist //FI "IMAGENAME eq py.exe"` (Bash) after killing, and fall back
to PowerShell `Stop-Process -Id <pid> -Force` if it's still running.

## Live smoke testing the GUI

```
py main.py
```

To check for a crash without watching the window: background it, wait a
few seconds, check the log is clean, then kill it (see process cleanup
above).

## Reference

- `masterplan-short.md` is this project's spec/plan/constitution doc —
  read it before making architectural changes.
- CC Cluster (`ve7cc.net`) protocol facts (verified filter commands, the
  literal `-#` skimmer-spot marker, etc.) live in `masterplan-short.md`'s
  Spec section — check there before assuming AR-Cluster syntax applies.
