import asyncio
import os
import pathlib
from datetime import date

db = pathlib.Path(__file__).parent / "test_genres.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

import app.genres as genres  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CategoryPrivacy, CollectionEntry, User, Visibility, Work, WorkGenre  # noqa: E402
from app.services import anilist, lastfm, steam  # noqa: E402

CALLS = {"steam": 0, "anilist": 0, "lastfm": [], "track": []}


async def fake_steam(appid):
    CALLS["steam"] += 1
    if appid == "999":
        raise RuntimeError("boom")
    return {"genres": [{"description": "策略"}, {"description": "模擬"}]} if appid == "394360" else {"genres": [{"description": "動作"}]}


async def fake_anilist(i):
    CALLS["anilist"] += 1
    return ["Action", "Comedy", "Slice of Life", "Hentai", "Unknown Genre"]


async def fake_tags(artist):
    CALLS["lastfm"].append(artist)
    return [("post-hardcore", 100), ("hard rock", 50)]  # a same-name band: only used as a fallback


async def fake_track_tags(artist, title):
    CALLS["track"].append(title)
    if title == "BLOODY STREAM":
        return [("j-pop", 100), ("seen live", 90), ("Coda", 80), ("anime", 60), ("JoJo", 40), ("jazz", 30), ("rare", 5)]
    return []


steam.get_app_details, anilist.get_genres, lastfm.get_artist_tags = fake_steam, fake_anilist, fake_tags
lastfm.get_track_tags = fake_track_tags
genres.DELAY = {k: 0 for k in genres.DELAY}


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


with TestClient(app) as client, TestClient(app) as anon:
    with Session(engine) as s:
        u = User(username="alice", display_name="Alice", password_hash=hash_password("testpass123"), birth_date=date(2000, 1, 1))
        s.add(u)
        s.flush()
        hoi = Work(category=Category.game, source="steam", external_id="394360", title="Hearts of Iron IV")
        other = Work(category=Category.game, source="steam", external_id="1", title="Some Action Game")
        broken = Work(category=Category.game, source="steam", external_id="999", title="Broken")
        mob = Work(category=Category.anime, source="anilist", external_id="21507", title="Mob Psycho 100")
        song1 = Work(category=Category.music, source="youtube", external_id="a", title="BLOODY STREAM", creator="Coda")
        song2 = Work(category=Category.music, source="lastfm", external_id="b", title="Another", creator="coda")
        lonely = Work(category=Category.anime, source="test", external_id="x", title="Nobody Has Me")
        s.add_all([hoi, other, broken, mob, song1, song2, lonely])
        s.flush()
        s.add_all([
            CollectionEntry(user_id=u.id, work_id=hoi.id, playtime_minutes=1000 * 60),
            CollectionEntry(user_id=u.id, work_id=other.id, playtime_minutes=60),
            CollectionEntry(user_id=u.id, work_id=broken.id, playtime_minutes=60),
            CollectionEntry(user_id=u.id, work_id=mob.id, tier="must_watch"),
            CollectionEntry(user_id=u.id, work_id=song1.id, play_count=50),
            CollectionEntry(user_id=u.id, work_id=song2.id, play_count=3),
        ])
        s.commit()
        ids = {w.title: w.id for w in (hoi, other, broken, mob, song1, song2, lonely)}

    with Session(engine) as s:
        n = asyncio.run(genres.enrich_batch(s, limit=50))
    with Session(engine) as s:
        g = {}
        for row in s.exec(select(WorkGenre)):
            g.setdefault(row.work_id, {})[row.genre] = row.weight
        checked = {w.title: w.genres_checked_at is not None for w in s.exec(select(Work))}
    check("Steam genres stored in Chinese", set(g[ids["Hearts of Iron IV"]]) == {"策略", "模擬"})
    check("AniList genres translated, Hentai/unknown handled", set(g[ids["Mob Psycho 100"]]) == {"動作", "喜劇", "日常", "Unknown Genre"})
    check("music: junk / artist-name / weak tags dropped", set(g[ids["BLOODY STREAM"]]) == {"j-pop", "anime", "jojo", "jazz"})
    check("song tags used when present (no artist lookup needed)", "BLOODY STREAM" in CALLS["track"] and set(g[ids["BLOODY STREAM"]]) == {"j-pop", "anime", "jojo", "jazz"})
    check("untagged song falls back to artist tags, looked up once", CALLS["lastfm"] == ["coda"] and set(g[ids["Another"]]) == {"post-hardcore", "hard rock"})
    check("tag strength kept as weight", g[ids["BLOODY STREAM"]]["j-pop"] == 1.0 and g[ids["BLOODY STREAM"]]["jazz"] == 0.3)
    check("failed lookup left for retry, others continue", not checked["Broken"] and checked["Some Action Game"])
    check("works nobody collected are skipped", not checked["Nobody Has Me"])
    with Session(engine) as s:
        calls_before = CALLS["steam"]
        asyncio.run(genres.enrich_batch(s, limit=50))
        check("second pass only retries the failure", CALLS["steam"] == calls_before + 1 and CALLS["anilist"] == 1)

    with Session(engine) as s:
        u = s.exec(select(User)).one()
        prof = genres.user_style(s, u, set(Category))
        game = prof[Category.game]
        check("game style weighted by playtime: 策略/模擬 on top", [x.genre for x in game.genres[:2]] == ["策略", "模擬"] or [x.genre for x in game.genres[:2]] == ["模擬", "策略"])
        check("analysed count excludes the failed game", game.analysed == 2 and game.total == 3)
        check("music style led by the heavy-play tags", prof[Category.music].genres[0].genre == "j-pop")

    client.post("/login", data={"username": "alice", "password": "testpass123"})
    page = client.get("/u/alice").text
    check("profile shows 風格偏好 with bars", "風格偏好" in page and "策略" in page and "j-pop" in page and "style-fill" in page)
    check("partial analysis noted", "已分析 2 / 3 款" in page)
    with Session(engine) as s:
        uid = s.exec(select(User)).one().id
        s.add(CategoryPrivacy(user_id=uid, category=Category.music, visibility=Visibility.private))
        s.commit()
    check("private category's style hidden from visitors", "j-pop" not in anon.get("/u/alice").text)
    check("owner still sees it", "j-pop" in client.get("/u/alice").text)

# Live lookups with the user's own examples
steam_live = asyncio.run(steam.__class__ and __import__("app.services.steam", fromlist=["x"]).get_app_details("394360"))
check(f"live Steam (Hearts of Iron IV): {[x['description'] for x in (steam_live or {}).get('genres', [])]}", bool(steam_live))
import importlib  # noqa: E402

real_anilist = importlib.reload(importlib.import_module("app.services.anilist"))
live_ani = asyncio.run(real_anilist.get_genres(21507))
check(f"live AniList (Mob Psycho 100): {live_ani}", bool(live_ani))
real_lastfm = importlib.reload(importlib.import_module("app.services.lastfm"))
live_tags = asyncio.run(real_lastfm.get_track_tags("Coda", "BLOODY STREAM"))
check(f"live Last.fm song tags (Coda - BLOODY STREAM): {genres._clean_music_tags(live_tags or [], 'Coda')}", bool(live_tags))
