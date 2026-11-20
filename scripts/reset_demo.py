"""Restore demo.db to its initial state before a demo: a copy of the snapshot that
`python -m scripts.seed_demo` built, with every timestamp moved forward to now (so the seeded chat
still reads "1 小時前"). Everything done during the last demo is gone — new picks, messages,
photos, game rooms, and demo's dismissed 本季新番 banner. No network needed.

Stop the demo server first (Windows keeps the file locked while it runs).
Usage: .venv\\Scripts\\python.exe -m scripts.reset_demo
"""

import sys

from scripts import demo_db


def main() -> int:
    try:
        shifted = demo_db.restore()
    except FileNotFoundError:
        print(f"{demo_db.SNAPSHOT.name} doesn't exist yet. Build it once with: python -m scripts.seed_demo")
        return 1
    except PermissionError:
        print(f"{demo_db.DEMO_DB.name} is in use. Stop the demo server (Ctrl+C) and run this again.")
        return 1
    when = f", times moved forward by {shifted.days} d {shifted.seconds // 3600} h" if shifted else ""
    print(f"{demo_db.DEMO_DB.name} restored from {demo_db.SNAPSHOT.name}{when}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
