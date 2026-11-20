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

# 新手教學 cover picker save: a built-in book is looked up over the network. It used to be looked up
# after an earlier pick was already written, so the lock was held across the await (live load test:
# "database is locked" for everyone else).
from app import quickpick  # noqa: E402
from app.services import books  # noqa: E402


async def fake_book_search(query):
    other_writer_can_commit(f"book search {query}")
    return []  # no record: saved from the list's title and author


books.search = fake_book_search
blocked.clear()
game = quickpick._fallback(Category.game)[0]
book_keys = [i.key for i in quickpick._fallback(Category.book)[:2]]
with Session(engine) as s:
    me = s.exec(select(User).where(User.username == "u")).one()
    result = asyncio.run(quickpick.save(s, me, [game.key, *book_keys], []))
check("picker saved the game and both books", (result.added, result.skipped) == (3, 0), str(result))
check("no lock held while looking up a picked book", not blocked, str(blocked))
with Session(engine) as s:
    picks = s.exec(select(CollectionEntry).where(CollectionEntry.quick_pick == True)).all()  # noqa: E712
    check("picks stored as quick picks", len(picks) == 3, str(len(picks)))

# Two people pick the same new work at the same moment: the other one's insert lands between our
# lookup and our insert (unique source + external_id). The save must retry, not fail with a 500.
real_work_for = quickpick._work_for
raced = []


def racing_work_for(session, item):
    if not raced:
        raced.append(item.key)
        with Session(engine) as other:
            other.add(Work(category=item.cat, source=item.source, external_id=item.external_id, title=item.title))
            other.commit()
        work = Work(category=item.cat, source=item.source, external_id=item.external_id, title=item.title)
        session.add(work)
        session.flush()  # what the old code did after its lookup missed: now a duplicate
        return work
    return real_work_for(session, item)


quickpick._work_for = racing_work_for
new_game = quickpick._fallback(Category.game)[1]
with Session(engine) as s:
    me = s.exec(select(User).where(User.username == "u")).one()
    try:
        result = asyncio.run(quickpick.save(s, me, [new_game.key], []))
        err = None
    except Exception as e:  # noqa: BLE001
        result, err = None, e
quickpick._work_for = real_work_for
check("same new work picked by two people at once: save retries", err is None and result.added == 1 and raced, repr(err))
with Session(engine) as s:
    rows = s.exec(select(Work).where(Work.source == new_game.source, Work.external_id == new_game.external_id)).all()
    mine = s.exec(select(CollectionEntry).where(CollectionEntry.work_id == rows[0].id)).all() if rows else []
    check("one shared work, and the pick points at it", len(rows) == 1 and len(mine) == 1, f"{len(rows)} works, {len(mine)} picks")

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
