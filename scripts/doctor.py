"""Environment health check for Spotter-test. Run first in any new session:

    py scripts/doctor.py

Checks Python resolution (flags the Microsoft Store stub), required
packages, PowerShell execution policy, and DX cluster reachability. On
success, writes scripts/env.json with the resolved absolute interpreter
path so every later command can invoke it directly - no `activate`, no
relying on `python`/`py` resolving the same way in a fresh shell.

Exits 0 if every check passes, 1 otherwise (with remediation steps).
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_JSON_PATH = REPO_ROOT / "scripts" / "env.json"
REQUIRED_PACKAGES = ["matplotlib", "requests"]


def _is_store_stub(path: str) -> bool:
    return "WindowsApps" in path


def check_python_resolution() -> tuple[bool, list[str]]:
    """Bare `python`/`python3` resolve to non-functional Microsoft Store
    stubs on this machine (they just open the Store instead of running
    Python) and must not be used. `py` (the Windows Python launcher) is
    the one that works - even though py.exe's own path also lives under
    WindowsApps, it's a legitimate forwarder there, not a broken stub, so
    path-location alone can't tell them apart. The only reliable test is
    empirical: what does invoking it actually resolve to? sys.executable
    inside *this* process (launched via `py`) is that ground truth."""
    print("== Python resolution ==")
    problems = []
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found is None:
            print(f"  {name}: not found on PATH")
            continue
        note = " (path is under WindowsApps - see note below)" if _is_store_stub(found) else ""
        print(f"  {name}: {found}{note}")

    resolved = sys.executable
    print(f"  resolved interpreter (this process, via `py`): {resolved}")
    if _is_store_stub(resolved):
        # This would mean `py` itself is broken (unlike the healthy case
        # above, where py.exe's WindowsApps path still forwards to a real
        # interpreter) - only fail on this actual, empirical outcome.
        problems.append(
            "`py` resolved to a Store-stub interpreter instead of a real "
            "one - the `py` launcher itself is broken. Reinstall Python "
            "from python.org (not the Microsoft Store)."
        )
    else:
        print("  (bare `python`/`python3` may show WindowsApps stub paths "
              "above - that's expected and fine; always invoke via `py`.)")
    return (len(problems) == 0, problems)


def check_packages() -> tuple[bool, list[str]]:
    print("== Required packages ==")
    problems = []
    for pkg in REQUIRED_PACKAGES:
        try:
            version = subprocess.run(
                [sys.executable, "-c", f"import importlib.metadata as m; print(m.version('{pkg}'))"],
                capture_output=True, text=True, timeout=10,
            )
            if version.returncode == 0:
                print(f"  {pkg}: {version.stdout.strip()}")
            else:
                print(f"  {pkg}: NOT INSTALLED")
                problems.append(
                    f"Missing package '{pkg}'. Install with: "
                    f"{sys.executable} -m pip install {pkg}"
                )
        except Exception as e:
            print(f"  {pkg}: check failed ({e})")
            problems.append(f"Could not verify '{pkg}': {e}")
    return (len(problems) == 0, problems)


def check_powershell_execution_policy() -> tuple[bool, list[str]]:
    """Informational only - this project invokes python directly (no
    activate.ps1), so a restrictive policy no longer blocks anything here.
    Still reported since other PowerShell automation in this repo
    (process cleanup, live probes) depends on PowerShell working at all."""
    print("== PowerShell execution policy ==")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-ExecutionPolicy"],
            capture_output=True, text=True, timeout=10,
        )
        policy = result.stdout.strip()
        print(f"  {policy or '(empty response)'}")
        if policy == "Restricted":
            print(
                "  note: Restricted blocks .ps1 scripts, but this project "
                "doesn't use any - informational only, not a failure."
            )
    except Exception as e:
        print(f"  could not check: {e}")
        return (False, [f"PowerShell did not respond: {e}"])
    return (True, [])


def check_cluster_reachable() -> tuple[bool, list[str]]:
    sys.path.insert(0, str(REPO_ROOT))
    from config import DEFAULTS

    host, port = DEFAULTS["host"], DEFAULTS["port"]
    print(f"== DX cluster reachability ({host}:{port}) ==")
    try:
        with socket.create_connection((host, port), timeout=10.0):
            print(f"  connected OK")
            return (True, [])
    except OSError as e:
        print(f"  FAILED: {e}")
        return (
            False,
            [
                f"Could not reach {host}:{port} - {e}. Check your internet "
                "connection, or the cluster may be temporarily down (try "
                "again in a few minutes)."
            ],
        )


def write_env_json(all_ok: bool) -> None:
    ENV_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "python_exe": sys.executable,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "all_checks_passed": all_ok,
    }
    ENV_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {ENV_JSON_PATH} (python_exe={sys.executable})")


def main() -> int:
    checks = [
        check_python_resolution,
        check_packages,
        check_powershell_execution_policy,
        check_cluster_reachable,
    ]
    all_problems: list[str] = []
    all_ok = True
    for check in checks:
        ok, problems = check()
        all_ok = all_ok and ok
        all_problems.extend(problems)
        print()

    write_env_json(all_ok)

    if all_problems:
        print("\n== Problems found ==")
        for p in all_problems:
            print(f"  - {p}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
