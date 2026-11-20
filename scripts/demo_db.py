"""Paths and copy logic for the demo database. No app imports, so resetting is instant and offline.

- demo.seed.db: the snapshot `python -m scripts.seed_demo` builds (needs the network once)
- demo.db: what the demo server uses; `python -m scripts.reset_demo` copies the snapshot over it
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DB = ROOT / "demo.db"
SNAPSHOT = ROOT / "demo.seed.db"
DEMO_URL = "sqlite:///demo.db"
SNAPSHOT_URL = "sqlite:///demo.seed.db"


def remove(db: Path) -> None:
    """Delete a SQLite file and its -wal / -shm / -journal side files."""
    for path in (db, *(db.with_name(db.name + suffix) for suffix in ("-wal", "-shm", "-journal"))):
        path.unlink(missing_ok=True)


def restore() -> None:
    """Make demo.db an exact copy of the snapshot. Raises FileNotFoundError without a snapshot and
    PermissionError when a running server still has demo.db open (Windows)."""
    if not SNAPSHOT.exists():
        raise FileNotFoundError(SNAPSHOT)
    remove(DEMO_DB)
    shutil.copyfile(SNAPSHOT, DEMO_DB)
