"""Run every tests/test_*.py and summarise.

Each suite is a plain script that prints PASS / FAIL lines and uses its own throwaway SQLite file
next to it (tests/*.db, git-ignored). External APIs are faked inside the suites, except a few
checks marked "live" that call real services and are skipped or tolerated when offline.

Usage (from the repo root):
    .venv\\Scripts\\python.exe tests\\run_all.py            # all suites
    .venv\\Scripts\\python.exe tests\\run_all.py season     # suites whose name contains "season"

test_youtube.py can also import a real Google Takeout export: set YODO_TAKEOUT_DIR to the
"YouTube 和 YouTube Music" folder. Without it those checks are skipped.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


def main() -> int:
    wanted = sys.argv[1:]
    suites = sorted(p for p in TESTS.glob("test_*.py") if not wanted or any(w in p.stem for w in wanted))
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "BACKGROUND_JOBS": "false"}
    total_pass = total_fail = 0
    broken = []
    for suite in suites:
        for db in TESTS.glob("*.db"):
            try:
                db.unlink()
            except OSError:
                pass  # still held by a crashed run; the suite deletes its own file again
        started = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(suite)], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
        )
        out = proc.stdout + proc.stderr
        lines = out.splitlines()
        passed = sum(line.startswith("PASS") for line in lines)
        failed = [line for line in lines if line.startswith("FAIL")]
        crashed = proc.returncode != 0 and "Traceback" in out
        total_pass += passed
        total_fail += len(failed)
        status = "ok" if not failed and not crashed else "FAILED"
        print(f"{suite.name:<24} {passed:>4} pass {len(failed):>3} fail  {time.perf_counter() - started:5.1f}s  {status}")
        for line in failed[:10]:
            print(f"    {line}")
        if crashed:
            broken.append(suite.name)
            tail = [line for line in lines if line.strip()][-3:]
            print("    crashed: " + " | ".join(tail))
    print(f"\nTOTAL {total_pass} pass, {total_fail} fail" + (f", crashed: {', '.join(broken)}" if broken else ""))
    return 1 if total_fail or broken else 0


if __name__ == "__main__":
    sys.exit(main())
