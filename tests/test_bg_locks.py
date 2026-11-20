"""Background lookups (genres, Chinese titles) must not hold a database lock while waiting on the
network. Route handlers commit synchronously on the same event loop, so a lock held across an
await turned into a 5-second hang and "database is locked" (seen when starting 猜歌 right after
the demo server started). Here, while each fake API call is in flight, a separate connection
writes with no wait at all."""

import asyncio
import os
import pathlib
import sqlite3

here = pathlib.Path(__file__).parent
db = here / "test_bg_locks.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from sqlmodel import Session, select  # noqa: E402

from app import anime_search, genres  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Category, CollectionEntry, User, Work, WorkGenre  # noqa: E402
from app.services import anilist, bangumi, steam  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


init_db()
with Session(engine) as s:
    u = User(username="u", display_name="U", password_hash="x")
    s.add(u)
    s.flush()
    for i in range(3):
        w = Work(category=Category.anime, source="anilist", external_id=str(100 + i), title=f"A{i}", original_title=f"番{i}")
        s.add(w)
        s.flush()
        s.add(CollectionEntry(user_id=u.id, work_id=w.id))
    g = Work(category=Category.game, source="steam", external_id="10", title="G")
    s.add(g)
    s.flush()
    s.add(CollectionEntry(user_id=u.id, work_id=g.id))
    s.commit()

blocked = []


def other_writer_can_commit(tag):
    """A different connection writes with a zero busy-timeout: fails at once if a lock is held."""
    con = sqlite3.connect(db, timeout=0)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("UPDATE user SET bio = ? WHERE username = 'u'", (tag,))
        con.commit()
    except sqlite3.OperationalError as e:
        blocked.append((tag, str(e)))
    finally:
        con.close()


async def fake_genres(anilist_id):
    other_writer_can_commit(f"genres {anilist_id}")
    await asyncio.sleep(0)
    return ["Drama", "Comedy", "Romance"]


async def fake_steam(appid):
    other_writer_can_commit(f"steam {appid}")
    return {"genres": [{"description": "RPG"}, {"description": "Action"}]}


async def fake_bangumi(native):
    other_writer_can_commit(f"bangumi {native}")
    return [bangumi.Subject(id=1, name=native, name_cn="中文名")]


anilist.get_genres, steam.get_app_details, bangumi.search_anime = fake_genres, fake_steam, fake_bangumi
genres.DELAY = {k: 0 for k in genres.DELAY}
anime_search.BANGUMI_DELAY = 0
# The politeness pauses between API calls are awaits too: check the lock there as well.
real_sleep = asyncio.sleep


async def checking_sleep(seconds, *a, **k):
    other_writer_can_commit("during the pause between API calls")
    await real_sleep(0)


asyncio.sleep = checking_sleep

with Session(engine) as s:
    n = asyncio.run(genres.enrich_batch(s))
check("genre pass processed every work", n == 4, str(n))
check("no lock held while waiting on the genre APIs", not blocked, str(blocked))
with Session(engine) as s:
    saved = {g.genre for g in s.exec(select(WorkGenre))}
    checked = all(w.genres_checked_at for w in s.exec(select(Work)))
check("genres still saved and marked checked", {"劇情", "Drama", "RPG"} & saved and checked, str(saved))

blocked.clear()
with Session(engine) as s:
    n = asyncio.run(anime_search.enrich_titles(s))
check("title pass processed the anime", n == 3, str(n))
check("no lock held while waiting on Bangumi", not blocked, str(blocked))
with Session(engine) as s:
    check("titles marked checked", all(w.zh_checked_at for w in s.exec(select(Work).where(Work.category == Category.anime))))

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
