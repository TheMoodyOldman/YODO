import io
import itertools
import json
import os
import pathlib
import re
import sqlite3
from datetime import datetime, timedelta

db = pathlib.Path(__file__).parent / "test_card.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import app.routers.card as card_router  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.main import app  # noqa: E402
from app.services import steam  # noqa: E402

GAMES = {"value": []}


async def fake_owned(steam_id):
    return GAMES["value"]


async def fake_verify(params):
    return "76561198000000009"


async def no_images(urls):  # keep tests offline; covers render as placeholders
    return {}


steam.get_owned_games = fake_owned
steam.verify_openid = fake_verify
card_router.fetch_images = no_images

now = datetime.now(TAIPEI)
this_month = now.strftime("%Y-%m")
prev = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def q(sql):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def approve_all(client, path):
    r = client.get(path)
    data = {k: re.findall(rf'name="{k}" value="([^"]+)"', r.text) for k in ("listed_artist", "artist", "listed_song", "song", "publish")}
    client.post(path, data={k: v for k, v in data.items() if v})


with TestClient(app) as alice, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "display_name": "Alice", "password": "testpass123", "birth_date": "2000-01-01"})

    r = alice.get("/me/card")
    check("no data -> friendly empty state", "還沒有可以做成 Recap 的資料" in r.text)
    check("card page requires login", anon.get("/me/card", follow_redirects=False).status_code == 303)

    # --- Steam monthly playtime
    GAMES["value"] = [
        steam.OwnedGame(413150, "Stardew Valley", 12000, playtime_2weeks=300),  # 5h recently
        steam.OwnedGame(1145360, "Hades", 600, playtime_2weeks=0),  # not played lately
        steam.OwnedGame(367520, "Hollow Knight", 90, playtime_2weeks=90),  # brand new
    ]
    r = alice.get("/me/steam/connect", follow_redirects=False)
    rt = re.search(r"openid.return_to=([^&]+)", r.headers["location"]).group(1)
    from urllib.parse import unquote, urlparse, parse_qs
    rt = unquote(rt)
    state = parse_qs(urlparse(rt).query)["state"][0]
    alice.get(urlparse(rt).path, params={"state": state, "openid.mode": "id_res", "openid.op_endpoint": steam.OPENID_URL,
                                          "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000009",
                                          "openid.return_to": rt})
    rows = dict((t, (s, e)) for t, s, e in q(
        "SELECT w.title, p.start_minutes, p.end_minutes FROM monthlyplaytime p JOIN work w ON w.id=p.work_id"))
    check("first sync credits last 2 weeks to this month", rows.get("Stardew Valley") == (11700, 12000))
    check("idle game gets no monthly row", "Hades" not in rows)
    check("new game: its 2-week time counts", rows.get("Hollow Knight") == (0, 90))

    GAMES["value"] = [
        steam.OwnedGame(413150, "Stardew Valley", 12240, playtime_2weeks=540),
        steam.OwnedGame(1145360, "Hades", 660, playtime_2weeks=60),
        steam.OwnedGame(367520, "Hollow Knight", 90, playtime_2weeks=90),
    ]
    alice.post("/me/steam/sync")
    rows = dict((t, (s, e)) for t, s, e in q(
        "SELECT w.title, p.start_minutes, p.end_minutes FROM monthlyplaytime p JOIN work w ON w.id=p.work_id"))
    check("re-sync extends the month's end", rows.get("Stardew Valley") == (11700, 12240))
    check("idle game starts from last known total", rows.get("Hades") == (600, 660))
    approve_all(alice, "/me/steam/review")

    # --- music across two months + anime
    def yt(vid, title, artist, month, n):
        return [{"header": "YouTube Music", "title": f"Watched {title}", "titleUrl": f"https://music.youtube.com/watch?v={vid}",
                 "subtitles": [{"name": f"{artist} - Topic"}], "time": f"{month}-10T04:00:00Z"} for _ in range(n)]
    hist = yt("AAAAAAAAAA1", "Old Favourite", "Band X", prev, 50) + yt("BBBBBBBBBB2", "New Crush", "Band Y", this_month, 7) \
        + yt("CCCCCCCCCC3", "Also New", "Band Y", this_month, 3) + yt("AAAAAAAAAA1", "Old Favourite", "Band X", this_month, 1)
    alice.post("/me/youtube/import", files={"history": ("watch-history.json", json.dumps(hist).encode(), "application/json")})
    approve_all(alice, "/me/music/review")
    r = alice.get("/me/collection", params={"q": "Frieren"})
    anilist_id = re.findall(r'name="anilist_id" value="(\d+)"', r.text)[0]
    alice.post("/me/collection/anime", data={"anilist_id": anilist_id})

    # --- card page
    r = alice.get("/me/card")
    months = re.findall(r'<option value="(\d{4}-\d{2})"', r.text)
    check("months listed newest first", months[:2] == [this_month, prev])
    img = re.search(r'class="card-preview" src="([^"]+)"', r.text)
    check("defaults to current month with preview", img is not None and this_month in img.group(1))
    url = img.group(1).replace("&amp;", "&")
    check("all three categories selected by default", all(f"c={c}" in url for c in ("music", "game", "anime")))

    r = alice.get(url)
    pic = Image.open(io.BytesIO(r.content))
    check("card image is a 1080x1920 JPEG", r.headers["content-type"] == "image/jpeg" and pic.size == (1080, 1920))

    from app.cards import Period, recap_stats
    from app.db import engine
    from sqlmodel import Session, select
    from app.models import Category, User
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "alice")).one()
        st = recap_stats(s, u, Period("month", this_month))
        check("music ranks by this month's plays, not lifetime",
              [w.title for _, w in st.songs] == ["New Crush", "Also New", "Old Favourite"] and st.total_plays == 11)
        check("top artist for the month", st.artists[0].name == "Band Y" and st.artists[0].plays == 10)
        check("games ranked by minutes this month",
              [(w.title, m) for w, m in st.games] == [("Stardew Valley", 540), ("Hollow Knight", 90), ("Hades", 60)])
        check("month games total", st.games_minutes == 690 and st.games_count == 3)
        check("anime added this month", st.anime_count == 1)
        old = recap_stats(s, u, Period("month", prev))
        check("previous month: music only", old.has(Category.music) and not old.games and not old.anime)

        year = this_month[:4]
        yr = recap_stats(s, u, Period("year", year))
        same_year = prev[:4] == year
        check("year sums its months", yr.total_plays == (61 if same_year else 11)
              and yr.songs[0][1].title == ("Old Favourite" if same_year else "New Crush"))

        ever = recap_stats(s, u, Period("all", "all"))
        check("all time: music sums every month", ever.total_plays == 61 and ever.songs[0][0].play_count == 51)
        check("all time: games use Steam lifetime totals",
              [(w.title, m) for w, m in ever.games] == [("Stardew Valley", 12240), ("Hades", 660), ("Hollow Knight", 90)]
              and ever.games_minutes == 12990 and ever.games_count == 3)

    # period switching on the page
    r = alice.get("/me/card", params={"period": "all"})
    img = re.search(r'class="card-preview" src="([^"]+)"', r.text).group(1).replace("&amp;", "&")
    check("all-time page selected, image uses period=all", 'aria-current="page">有史以來' in r.text and "period=all" in img)
    pic = Image.open(io.BytesIO(alice.get(img).content))
    check("all-time card renders 1080x1920", pic.size == (1080, 1920))
    r = alice.get("/me/card", params={"period": "year"})
    check("year page offers a year picker", 'name="year"' in r.text and f'value="{this_month[:4]}"' in r.text)
    check("month notice explains tracked-only playtime", "想看累計總時數請選「有史以來」" in alice.get("/me/card").text)

    # entry points
    page = alice.get("/u/alice").text
    check("owner profile has the Recap button", 'class="btn recap-btn"' in page and "製作我的 Recap" in page)
    check("visitors don't see the Recap button", "recap-btn" not in anon.get("/u/alice").text)
    check("nav says Recap", re.search(r'<a href="/me/card"[^>]*>.*?Recap</a>', page, re.S) is not None)

    # privacy default + filters
    alice.post("/me/settings", data={"display_name": "Alice", "visibility_game": "private",
                                     "visibility_anime": "public", "visibility_music": "public"})
    r = alice.get("/me/card")
    url = re.search(r'class="card-preview" src="([^"]+)"', r.text).group(1).replace("&amp;", "&")
    check("private category left out by default", "c=game" not in url and "c=music" in url and "（個人頁設為僅自己）" in r.text)
    r = alice.get("/me/card", params=[("month", this_month), ("c", ""), ("c", "game")])
    check("user can still opt a private category in", "c=game" in r.text and "c=music" not in r.text.split("card-preview")[1][:300])
    r = alice.get("/me/card", params=[("month", this_month), ("c", "")])
    check("nothing selected -> hint, no image", "至少選一個類別" in r.text and "card-preview\"" not in r.text)
    check("image 404 for no categories", alice.get("/me/card/image.jpg", params={"period": "month", "key": this_month}).status_code == 404)
    check("image 404 for bad key", alice.get("/me/card/image.jpg", params={"period": "month", "key": "../x", "c": "music"}).status_code == 404)
    check("image requires login", anon.get(url, follow_redirects=False).status_code == 303)

    # events
    r1 = alice.post("/me/card/events", json={"period": "all", "key": "all", "action": "share"})
    r2 = alice.post("/me/card/events", json={"period": "month", "key": this_month, "action": "hack"})
    r3 = alice.post("/me/card/events", json={"period": "year", "key": "20x6", "action": "share"})
    check("share event logged with period, bad input rejected", r1.status_code == 204 and r2.status_code == 422
          and r3.status_code == 422 and q("SELECT period, month, action FROM cardevent") == [("all", "all", "share")])

# --- every period, section combination and item count renders without overflow
from types import SimpleNamespace as NS  # noqa: E402
from app.card_render import render_card  # noqa: E402
from app.cards import Period, RecapStats  # noqa: E402
from app.models import Category  # noqa: E402
from app.music import ArtistStat  # noqa: E402

w = NS(title="T" * 80, cover_url=None, creator="A" * 60)
ok = True
for period in (Period("month", "2026-10"), Period("year", "2026"), Period("all", "all")):
    for n in (1, 5):
        st = RecapStats(period=period, artists=[ArtistStat("a", "A" * 60, 9, 1, None)],
                        songs=[(NS(play_count=3, added_at=None), w)] * n, total_plays=3,
                        games=[(w, 600000)] * n, games_minutes=99999999, games_count=999,
                        anime=[(NS(tier="must_watch", tag="我看了什麼"), w)] * min(n * 2, 8), anime_count=n)
        for k in (1, 2, 3):
            for cats in itertools.combinations(list(Category), k):
                try:
                    Image.open(io.BytesIO(render_card(st, "名" * 40, "example.com/u/x", set(cats), {}))).verify()
                except Exception as e:
                    ok = False
                    print("   render failed:", period.kind, n, cats, e)
check("all periods x section combinations render (long text, 1 and 5 items)", ok)
