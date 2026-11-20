"""Demo environment: the database-backed list cache (fresh / stale / never cached), the season list
working with AniList and Bangumi both down once prefetched, reset_demo restoring demo.db from the
snapshot, and remove_demo_people deleting demo_ accounts with everything pointing at them while
leaving real users' data alone. External APIs are faked."""

import asyncio
import os
import pathlib
from datetime import date, datetime, timedelta

here = pathlib.Path(__file__).parent
db = here / "test_demo_env.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import anime_search, catalog, seasonal  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Activity, ActivityKind, CatalogCache, Category, CollectionEntry, Comment, FriendStatus, Friendship, GameInvite,
    GameRoom, Message, RoomPlayer, User, Work, utcnow,
)
from app.services import anilist  # noqa: E402
from scripts import demo_db, remove_demo_people, reset_demo  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


init_db()
seasonal.local_today = lambda: date(2026, 11, 13)

# ---------- catalog cache ----------
calls = []


async def ok_fetch():
    calls.append(1)
    return [1, 2, 3]


async def broken_fetch():
    calls.append(1)
    raise anilist.AniListError("down")


async def run(coro):
    return await coro


with Session(engine) as s:
    v = asyncio.run(catalog.cached(s, "t", timedelta(hours=1), ok_fetch, (anilist.AniListError,)))
    v2 = asyncio.run(catalog.cached(s, "t", timedelta(hours=1), ok_fetch, (anilist.AniListError,)))
    check("fresh cache: fetched once, then served from the database", v == v2 == [1, 2, 3] and len(calls) == 1)
    row = s.get(CatalogCache, "t")
    row.fetched_at = utcnow() - timedelta(days=2)
    s.add(row)
    s.commit()
    v3 = asyncio.run(catalog.cached(s, "t", timedelta(hours=1), broken_fetch, (anilist.AniListError,)))
    check("stale cache + API down: stale copy served", v3 == [1, 2, 3] and len(calls) == 2)
    try:
        asyncio.run(catalog.cached(s, "never", timedelta(hours=1), broken_fetch, (anilist.AniListError,)))
        check("nothing cached + API down: error reaches the caller", False)
    except anilist.AniListError:
        check("nothing cached + API down: error reaches the caller", True)
    v4 = asyncio.run(catalog.cached(s, "t", timedelta(hours=1), ok_fetch, (anilist.AniListError,)))
    fresh = s.get(CatalogCache, "t")
    check("stale cache + API back: refreshed", v4 == [1, 2, 3] and catalog._age(fresh) < timedelta(minutes=1))

# ---------- season list survives restarts and outages once prefetched ----------
SHOWS = [anilist.Anime(id=500 + i, title=f"Show {i}", original_title=f"番組{i}", cover_url=None, year=2026, format="TV")
         for i in range(6)]
season_calls, zh_calls = [], []


async def fake_season(season, year, per_page=50):
    season_calls.append((season, year))
    return list(SHOWS)


async def fake_zh(native):
    zh_calls.append(native)
    return {"番組0": "節目零", "番組1": "節目一"}.get(native)


anilist.season_anime, anime_search.chinese_title = fake_season, fake_zh
with Session(engine) as s:
    n = asyncio.run(seasonal.prefetch(s, "2026-FALL"))
check("prefetch caches the list and looks up every title", n == 6 and len(zh_calls) == 6 and len(season_calls) == 1)


async def down(*a, **k):
    raise anilist.AniListError("down")


async def no_bangumi(native):
    raise AssertionError("Bangumi must not be called")


anilist.season_anime, anime_search.chinese_title = down, no_bangumi
with Session(engine) as s:  # cache made stale on purpose: AniList is down, the stored list is used
    row = s.get(CatalogCache, "season:2026-FALL")
    row.fetched_at = utcnow() - timedelta(days=3)
    s.add(row)
    s.commit()

c = TestClient(app)
c.post("/register", data={"username": "realone", "email": "realone@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
r = c.get("/me/season")
check("pick page works with AniList and Bangumi down", r.status_code == 200 and r.text.count('<input type="checkbox" name="pick"') == 6)
check("Chinese titles come from the cache", "節目零" in r.text and "節目一" in r.text and "Show 2" in r.text)
r = c.post("/me/season", data={"pick": ["500", "501"]}, follow_redirects=False)
with Session(engine) as s:
    picked = s.exec(select(Work).join(CollectionEntry).where(CollectionEntry.season == "2026-FALL")).all()
check("saving picks works offline, with the cached Chinese title", r.status_code == 303 and {w.title for w in picked} == {"節目零", "節目一"}
      and all(w.zh_checked_at for w in picked))

# ---------- remove_demo_people ----------
with Session(engine) as s:
    real = s.exec(select(User).where(User.username == "realone")).one()
    other = User(username="demo", display_name="Demo", password_hash="x")  # the demo account itself stays
    fake = User(username="demo_rain", display_name="小雨", password_hash="x")
    lookalike = User(username="demoXrain", display_name="Not fake", password_hash="x")  # "_" is a LIKE wildcard
    s.add_all([other, fake, lookalike])
    s.flush()
    work = s.exec(select(Work)).first()
    s.add(CollectionEntry(user_id=fake.id, work_id=work.id, tier="great"))
    s.add(Friendship(requester_id=real.id, addressee_id=fake.id, status=FriendStatus.accepted))
    act = Activity(user_id=fake.id, kind=ActivityKind.season_picks, day="2026-11-13", note="2026-FALL")
    s.add(act)
    s.flush()
    s.add(Comment(activity_id=act.id, user_id=real.id, body="我也在追"))  # real user's comment on a fake's item
    real_act = Activity(user_id=real.id, kind=ActivityKind.season_picks, day="2026-11-13", note="2026-FALL")
    s.add(real_act)
    s.flush()
    s.add(Comment(activity_id=real_act.id, user_id=fake.id, body="一起追"))  # fake's comment on a real item
    s.add(Message(sender_id=fake.id, recipient_id=real.id, body="hi"))
    room = GameRoom(code="ZZZZZZ", kind="song", host_id=fake.id)
    s.add(room)
    s.flush()
    s.add(RoomPlayer(room_id=room.id, user_id=fake.id, seat=0))
    s.add(RoomPlayer(room_id=room.id, user_id=real.id, seat=1))
    s.add(GameInvite(room_id=room.id, from_id=fake.id, to_id=real.id))
    s.commit()
    real_entries = len(s.exec(select(CollectionEntry).where(CollectionEntry.user_id == real.id)).all())

remove_demo_people.main(apply=False)
with Session(engine) as s:
    check("dry run deletes nothing", s.exec(select(User).where(User.username == "demo_rain")).first() is not None)
remove_demo_people.main(apply=True)
with Session(engine) as s:
    names = {u.username for u in s.exec(select(User))}
    check("demo_ account removed; demo and look-alikes kept", "demo_rain" not in names and {"demo", "demoXrain", "realone"} <= names)
    check("its entries, friendship, activity, message and hosted room are gone",
          not s.exec(select(Friendship)).all() and not s.exec(select(Message)).all() and not s.exec(select(GameRoom)).all()
          and not s.exec(select(RoomPlayer)).all() and not s.exec(select(GameInvite)).all()
          and {a.user_id for a in s.exec(select(Activity))} == {real.id})
    comments = s.exec(select(Comment)).all()
    check("comments on its activity and by it are gone", comments == [])
    check("real user's own collection untouched",
          len(s.exec(select(CollectionEntry).where(CollectionEntry.user_id == real.id)).all()) == real_entries == 2)
    check("works stay (shared catalog)", s.exec(select(Work)).first() is not None)

# ---------- reset_demo ----------
tmp_db, tmp_snap = here / "test_demo_live.db", here / "test_demo_seed.db"
for p in (tmp_db, tmp_snap):
    p.unlink(missing_ok=True)
demo_db.DEMO_DB, demo_db.SNAPSHOT = tmp_db, tmp_snap
check("reset without a snapshot explains how to build one", reset_demo.main() == 1 and not tmp_db.exists())
tmp_snap.write_bytes(b"snapshot-v1")
tmp_db.write_bytes(b"changed during the demo")
(tmp_db.with_name(tmp_db.name + "-wal")).write_bytes(b"stale wal")
check("reset restores demo.db from the snapshot", reset_demo.main() == 0 and tmp_db.read_bytes() == b"snapshot-v1")
check("reset removes the stale -wal file", not tmp_db.with_name(tmp_db.name + "-wal").exists())

# timestamps move forward by (reset time - seed time); dates of birth stay
import sqlite3  # noqa: E402

tmp_snap.unlink()
con = sqlite3.connect(tmp_snap)
con.executescript("""
CREATE TABLE catalogcache (key VARCHAR PRIMARY KEY, payload VARCHAR, fetched_at DATETIME);
CREATE TABLE message (id INTEGER PRIMARY KEY, created_at DATETIME, read_at DATETIME);
CREATE TABLE user (id INTEGER PRIMARY KEY, birth_date DATE, created_at DATETIME);
CREATE TABLE activity (id INTEGER PRIMARY KEY, day VARCHAR, updated_at DATETIME);
INSERT INTO catalogcache VALUES ('demo:seeded_at', '{}', '2026-11-13 12:00:00.000000');
INSERT INTO message VALUES (1, '2026-11-13 11:00:00.000000', NULL);
INSERT INTO user VALUES (1, '2000-01-01', '2026-11-13 12:00:00.000000');
INSERT INTO activity VALUES (1, '2026-11-13', '2026-11-13 11:30:00.000000');
""")
con.commit()
con.close()
real_shift = demo_db.shift_times
demo_db.shift_times = lambda db: real_shift(db, now=datetime(2026, 11, 21, 2, 0))  # 10:00 Taipei on demo day
try:
    ok = reset_demo.main() == 0
finally:
    demo_db.shift_times = real_shift
con = sqlite3.connect(tmp_db)
msg = con.execute("SELECT created_at, read_at FROM message").fetchone()
user = con.execute("SELECT birth_date, created_at FROM user").fetchone()
day = con.execute("SELECT day FROM activity").fetchone()[0]
con.close()
check("reset moves times forward: the 1-hour-old message is still 1 hour old",
      ok and msg[0].startswith("2026-11-21 01:00:00") and msg[1] is None, str(msg))
check("reset keeps dates of birth, moves sign-up time", user[0] == "2000-01-01" and user[1].startswith("2026-11-21 02:00:00"), str(user))
check("reset moves activity days (Taipei dates)", day == "2026-11-21", day)
check("database without a seed marker is copied unchanged", demo_db.shift_times(tmp_snap.with_name("missing.db")) is None)
for p in (tmp_db, tmp_snap, tmp_snap.with_name("missing.db")):
    p.unlink(missing_ok=True)

# the real snapshot (if built) only holds demo accounts and starts with the banner not dismissed
real_snapshot = pathlib.Path(__file__).resolve().parent.parent / "demo.seed.db"
if real_snapshot.exists():
    import sqlite3

    con = sqlite3.connect(real_snapshot)
    users = [r[0] for r in con.execute("SELECT username FROM user")]
    banner = con.execute("SELECT season_banner_dismissed FROM user WHERE username = 'demo'").fetchone()
    cached = con.execute("SELECT count(*) FROM catalogcache WHERE key LIKE 'season:%'").fetchone()[0]
    con.close()
    check("demo.seed.db only has demo / demo_ accounts", users and all(u == "demo" or u.startswith("demo_") for u in users))
    check("demo.seed.db: demo's 本季新番 banner not dismissed", banner == (None,))
    check("demo.seed.db: season list cached for offline use", cached >= 1)
else:
    print("SKIP demo.seed.db checks (build it with python -m scripts.seed_demo)")

# start_demo.ps1: Windows PowerShell 5.1 needs a BOM to read the Chinese text; it must reset first,
# serve demo.db with local assets on all interfaces, and only ever stop Python on its own port.
ps1 = pathlib.Path(__file__).resolve().parent.parent / "start_demo.ps1"
raw = ps1.read_bytes()
text = raw.decode("utf-8-sig")
check("start_demo.ps1 saved with a UTF-8 BOM", raw.startswith(b"\xef\xbb\xbf"))
check("start_demo.ps1 resets, then serves demo.db + local assets on 0.0.0.0:8000",
      text.index("scripts.reset_demo") < text.index("uvicorn app.main:app")
      and '$env:DATABASE_URL = "sqlite:///demo.db"' in text and '$env:LOCAL_ASSETS_DIR = "demo_assets"' in text
      and "--host 0.0.0.0 --port $Port" in text and "$Port = 8000" in text)
check("start_demo.ps1 only stops Python processes, and stops if the reset fails",
      "-match '^(python|pythonw|uvicorn)$'" in text and "if ($LASTEXITCODE -ne 0)" in text)
check("start_demo.ps1 prints private LAN addresses only", r"'^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)'" in text)

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
