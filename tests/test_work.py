import asyncio
import json
import os
import pathlib
import re
import sqlite3

db = pathlib.Path(__file__).parent / "test_work.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

import app.routers.me as me_router  # noqa: E402
import app.routers.work as work_router  # noqa: E402
from app.main import app  # noqa: E402
from app.services import anilist, steam  # noqa: E402
from app.workinfo import WorkInfo, get_work_info  # noqa: E402

FAKE = {i: anilist.Anime(i, f"Show {i}", f"番{i}", None, 2020, "TV") for i in range(1, 4)}


async def fake_get(i):
    return FAKE.get(i)


async def fake_info(work):
    return WorkInfo(description="<desc>", facts=[("開發", "ConcernedApe")], genres=["獨立"], link=("https://x.test/", "外部連結"))


async def fake_owned(steam_id):
    return [steam.OwnedGame(413150, "Stardew Valley", 12000, 300), steam.OwnedGame(1145360, "Hades", 600, 0)]


me_router.anilist.get_anime = fake_get
work_router.get_work_info = fake_info
steam.get_owned_games = fake_owned


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def q(sql, *args):
    con = sqlite3.connect(db)
    try:
        r = con.execute(sql, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


with TestClient(app) as alice, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})

    # adding an anime opens the rating dialog for it
    r = alice.post("/me/collection/anime", data={"anilist_id": "1", "q": "show"}, follow_redirects=False)
    loc = r.headers["location"]
    check("add redirects with ?rate= to anime tab", "rate=" in loc and "q=show" in loc and loc.endswith("#anime"))
    page = alice.get(loc.split("#")[0]).text
    check("dialog auto-opens for the new entry", "data-autoopen" in page and 'id="rate-dialog-anime"' in page and "Show 1" in page)
    check("dialog returns to the search results", 'name="next" value="/me/collection?q=show#anime"' in page)
    check("picker uses chips, not dropdowns", 'class="chip"' in page and "<select name=\"tier\"" not in page)
    check("removed tags gone, renamed tags present", "#霸權" not in page and "#糞作" not in page and "#好甜" in page and "#崩</label>" in page)
    r = alice.post("/me/collection/anime", data={"anilist_id": "1"}, follow_redirects=False)
    check("re-adding an owned anime doesn't reopen the dialog", "rate=" not in r.headers["location"])
    for i in (2, 3):
        alice.post("/me/collection/anime", data={"anilist_id": str(i)})
    ids = {t: int(e) for e, t in q("SELECT e.id, w.title FROM collectionentry e JOIN work w ON w.id = e.work_id")}

    # verdict endpoint
    r = alice.post(f"/me/collection/{ids['Show 1']}/verdict", data={"tier": "great", "tag": "胃痛", "next": "/me/collection?q=show#anime"}, follow_redirects=False)
    check("dialog save redirects to next", r.status_code == 303 and r.headers["location"] == "/me/collection?q=show#anime")
    r = alice.post(f"/me/collection/{ids['Show 2']}/verdict", data={"tier": "must_watch", "tag": "神作"}, headers={"X-Requested-With": "fetch"})
    check("autosave gets 204", r.status_code == 204)
    r = alice.post(f"/me/collection/{ids['Show 3']}/verdict", data={"tier": "x", "tag": "霸權", "next": "//evil.test"}, follow_redirects=False)
    check("bad values cleared, open redirect blocked", r.headers["location"] == "/me/collection#anime"
          and q("SELECT tier, tag FROM collectionentry WHERE id=?", ids["Show 3"]) == [(None, None)])
    r = anon.post(f"/me/collection/{ids['Show 1']}/verdict", data={"tier": "bad"}, follow_redirects=False)
    check("verdict requires login", r.status_code == 303 and "/login" in r.headers["location"])

    # hidden toggle no longer wipes verdicts
    alice.post(f"/me/collection/{ids['Show 1']}", data={})
    check("row save keeps verdict", q("SELECT tier, tag FROM collectionentry WHERE id=?", ids["Show 1"]) == [("great", "胃痛")])

    # games: no rating UI, verdict endpoint refuses
    alice.get("/me/steam/connect", follow_redirects=False)
    q("UPDATE user SET steam_id='76561198000000001'")
    alice.post("/me/steam/sync")
    r = alice.get("/me/steam/review")
    alice.post("/me/steam/review", data={"publish": re.findall(r'name="publish" value="(\d+)"', r.text)})
    games = {t: int(e) for e, t in q("SELECT e.id, w.title FROM collectionentry e JOIN work w ON w.id=e.work_id WHERE w.category='game'")}
    page = alice.get("/me/collection").text
    check("no star ratings anywhere", 'name="rating"' not in page and "★" not in page)
    r = alice.post(f"/me/collection/{games['Stardew Valley']}/verdict", data={"tier": "great"})
    check("verdict on a game is rejected", r.status_code == 400)

    # detail pages
    stardew = q("SELECT id FROM work WHERE title='Stardew Valley'")[0][0]
    hades = q("SELECT id FROM work WHERE title='Hades'")[0][0]
    r = anon.get(f"/u/alice/w/{stardew}")
    check("game page renders with records + info", r.status_code == 200 and "200 小時" in r.text and "第 1 / 2" in r.text
          and "ConcernedApe" in r.text and "&lt;desc&gt;" in r.text)
    check("game page has next arrow only", f'href="/u/alice/w/{hades}"' in r.text and 'data-nav="prev"' not in r.text)
    check("monthly history shown", "每月遊玩時數" in r.text and "5.0 小時" in r.text)
    check("visitor sees no picker", 'class="picker"' not in r.text)

    show2 = q("SELECT id FROM work WHERE title='Show 2'")[0][0]
    show1 = q("SELECT id FROM work WHERE title='Show 1'")[0][0]
    r = alice.get(f"/u/alice/w/{show2}")
    check("owner anime page has autosave picker", "data-autosave" in r.text and 'value="must_watch" id="work-tier-must_watch" checked' in r.text)
    check("anime page ordered by tier (Show 2 first, next Show 1)", "第 1 / 3" in r.text and f'href="/u/alice/w/{show1}"' in r.text)
    check("backdrop uses category color", "--work-color: #ec4899" in r.text)

    # music page
    hist = [{"header": "YouTube Music", "title": "Watched Song A", "titleUrl": "https://music.youtube.com/watch?v=AAAAAAAAAA1",
             "subtitles": [{"name": "Band - Topic"}], "time": "2026-09-10T00:00:00Z"}] * 4
    alice.post("/me/youtube/import", files={"history": ("watch-history.json", json.dumps(hist).encode(), "application/json")})
    r = alice.get("/me/music/review")
    alice.post("/me/music/review", data={k: re.findall(rf'name="{k}" value="([^"]+)"', r.text) for k in ("listed_artist", "artist", "listed_song", "song")})
    song = q("SELECT id FROM work WHERE title='Song A'")[0][0]
    r = anon.get(f"/u/alice/w/{song}")
    check("music page shows plays + monthly history", r.status_code == 200 and "4 <small>次播放</small>" in r.text and "2026/09" in r.text)

    # profile links to detail pages
    prof = anon.get("/u/alice").text
    check("profile cards link to detail pages", f'href="/u/alice/w/{stardew}"' in prof and f'href="/u/alice/w/{song}"' in prof)

    # privacy
    alice.post(f"/me/collection/{games['Hades']}", data={"hidden": "true"})
    check("hidden item 404 for visitors", anon.get(f"/u/alice/w/{hades}").status_code == 404)
    r = alice.get(f"/u/alice/w/{hades}")
    check("owner still sees hidden item", r.status_code == 200 and "已隱藏" in r.text)
    alice.post("/me/settings", data={"display_name": "alice", "visibility_game": "private", "visibility_anime": "public", "visibility_music": "public"})
    check("private category 404 for visitors", anon.get(f"/u/alice/w/{stardew}").status_code == 404)
    check("unknown work 404", anon.get("/u/alice/w/99999").status_code == 404)

    # tag migration on startup
    q("UPDATE collectionentry SET tag='發糖' WHERE id=?", ids["Show 1"])
    q("UPDATE collectionentry SET tag='霸權' WHERE id=?", ids["Show 2"])

with TestClient(app):
    pass  # restart runs init_db
check("old tags migrated on startup", q("SELECT id, tag FROM collectionentry WHERE id IN (?, ?) ORDER BY id", ids["Show 1"], ids["Show 2"])
      == sorted([(ids["Show 1"], "好甜"), (ids["Show 2"], None)]))

# Live metadata (network): Steam store, AniList, Last.fm
from app.models import Work  # noqa: E402

live = asyncio.run(get_work_info(Work(category="game", source="steam", external_id="413150", title="Stardew Valley")))
check(f"live Steam info: {len(live.facts)} facts, {len(live.genres)} genres", bool(live.facts) and bool(live.description))
live = asyncio.run(get_work_info(Work(category="anime", source="anilist", external_id="154587", title="Frieren")))
check(f"live AniList info: color {live.color}", bool(live.facts) and bool(live.color))
live = asyncio.run(get_work_info(Work(category="music", source="youtube", external_id="HyHNuVaZJ-k", title="Feel Good Inc.", creator="Gorillaz")))
check(f"live Last.fm track info: {live.facts[:1]}", bool(live.facts))
