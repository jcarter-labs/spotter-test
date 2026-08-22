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
