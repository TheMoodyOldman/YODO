"""Paths and copy logic for the demo database. No app imports, so resetting is instant and offline.

- demo.seed.db: the snapshot `python -m scripts.seed_demo` builds (needs the network once)
- demo.db: what the demo server uses; `python -m scripts.reset_demo` copies the snapshot over it

Restoring also moves every timestamp forward by the time since the snapshot was built, so a chat
seeded as "1 小時前" still reads "1 小時前" on demo day instead of "6 天前".
"""

import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DB = ROOT / "demo.db"
SNAPSHOT = ROOT / "demo.seed.db"
DEMO_URL = "sqlite:///demo.db"
SNAPSHOT_URL = "sqlite:///demo.seed.db"
SEEDED_AT_KEY = "demo:seeded_at"  # a catalogcache row whose fetched_at is when the snapshot was built
TAIPEI = timezone(timedelta(hours=8))


def remove(db: Path) -> None:
    """Delete a SQLite file and its -wal / -shm / -journal side files."""
    for path in (db, *(db.with_name(db.name + suffix) for suffix in ("-wal", "-shm", "-journal"))):
        path.unlink(missing_ok=True)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T")).replace(tzinfo=None)


def shift_times(db: Path, now: datetime | None = None) -> timedelta | None:
    """Move all DATETIME columns (and activity.day) forward by now - seeded_at. Dates of birth and
    other DATE columns stay. Returns the shift, or None when the database has no seed marker."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)  # stored datetimes are naive UTC
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT fetched_at FROM catalogcache WHERE key = ?", (SEEDED_AT_KEY,)).fetchone()
    except sqlite3.DatabaseError:
        con.close()
        return None  # not a seeded demo database
    if not row:
        con.close()
        return None
    seeded = _parse(row[0])
    delta = now - seeded
    seconds = int(delta.total_seconds())
    days = (now.replace(tzinfo=timezone.utc).astimezone(TAIPEI).date()
            - seeded.replace(tzinfo=timezone.utc).astimezone(TAIPEI).date()).days
    with con:
        tables = [t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            for _, column, declared, *_ in con.execute(f'PRAGMA table_info("{table}")').fetchall():
                if declared.upper() == "DATETIME":
                    con.execute(
                        f'UPDATE "{table}" SET "{column}" = strftime(\'%Y-%m-%d %H:%M:%f\', "{column}", ?) '
                        f'WHERE "{column}" IS NOT NULL',
                        (f"{seconds:+d} seconds",),
                    )
        if "activity" in tables and days:
            con.execute("UPDATE activity SET day = date(day, ?) WHERE day IS NOT NULL", (f"{days:+d} days",))
    con.close()
    return delta


def restore() -> timedelta | None:
    """Make demo.db a copy of the snapshot with its timestamps moved to now. Raises FileNotFoundError
    without a snapshot and PermissionError when a running server still has demo.db open (Windows)."""
    if not SNAPSHOT.exists():
        raise FileNotFoundError(SNAPSHOT)
    remove(DEMO_DB)
    shutil.copyfile(SNAPSHOT, DEMO_DB)
    return shift_times(DEMO_DB)
