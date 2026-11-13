import asyncio
import json
import os
import pathlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

db = pathlib.Path(__file__).parent / "test_lastfm.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.main import app  # noqa: E402
from app.services import lastfm  # noqa: E402

real_secret = settings.lastfm_shared_secret
real_call = lastfm._call


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def ts(y, m, d, h=12):
    return str(int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()))


def track(artist, name, uts, image="https://lastfm.freetls.fastly.net/i/u/300x300/abc.jpg", nowplaying=False):
    t = {"artist": {"#text": artist, "mbid": ""}, "name": name, "album": {"#text": "X"},
         "image": [{"size": "small", "#text": image}, {"size": "extralarge", "#text": image}]}
    if nowplaying:
        t["@attr"] = {"nowplaying": "true"}
    else:
        t["date"] = {"uts": uts, "#text": ""}
    return t


PLACEHOLDER = "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
SCENARIO = {"pages": [], "private": False, "username": "RealFan"}
CALLS = []


async def fake_call(client, params):
    CALLS.append(dict(params))
    if params["method"] == "auth.getSession":
        if params["token"] == "good-token":
            return {"session": {"name": SCENARIO["username"], "key": "k", "subscriber": 0}}
        raise lastfm.LastfmError("4: Invalid authentication token")
    if SCENARIO["private"]:
        raise lastfm.LastfmPrivate("Login: User required to be logged in")
    pages = SCENARIO["pages"]
    page = int(params["page"])
    return {"recenttracks": {"track": pages[page - 1] if pages else [],
                             "@attr": {"page": str(page), "totalPages": str(len(pages)), "total": "0"}}}


lastfm._call = fake_call
settings.lastfm_shared_secret = "test-secret"


def connect(client):
    r = client.get("/me/lastfm/connect", follow_redirects=False)
    loc = r.headers["location"]
    cb = parse_qs(urlparse(loc).query)["cb"][0]
    return loc, cb


def callback(client, cb, token):
    state = parse_qs(urlparse(cb).query)["state"][0]
    return client.get(urlparse(cb).path, params={"state": state, "token": token})


now = datetime.now(TAIPEI)
this_month = now.strftime("%Y-%m")

with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    bob.post("/register", data={"username": "bob", "email": str("bob").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})

    loc, cb = connect(alice)
    check("connect -> Last.fm auth URL with api_key + cb", loc.startswith(lastfm.AUTH_URL) and "api_key=" in loc and "state=" in cb)

    r = alice.get(urlparse(cb).path, params={"state": "forged", "token": "good-token"})
    check("forged state rejected", "已失效" in r.text)
    loc, cb = connect(alice)
    r = callback(alice, cb, "bad-token")
    check("invalid token rejected", "驗證失敗" in r.text)

    # first sync: 2 pages, now-playing entry, single-dict page, placeholder art, month boundary in Taipei
    recent = int((now - timedelta(days=1)).timestamp())
    SCENARIO["pages"] = [
        [track("Gorillaz", "DARE", "", nowplaying=True),
         track("Gorillaz", "DARE", str(recent)),
         track("gorillaz", "dare", str(recent - 60)),
         track("Coda", "BLOODY STREAM", str(recent - 120), image=PLACEHOLDER)],
        track("Coda", "BLOODY STREAM", ts(2026, 8, 31, 17)),  # single dict, = Sep 1 01:00 Taipei
    ]
    CALLS.clear()
    loc, cb = connect(alice)
    r = callback(alice, cb, "good-token")
    check("link + first sync -> review", str(r.url).endswith("/me/music/review") and "新增 2 首歌" in r.text and "共 4 次播放" in r.text)
    first_from = datetime.fromtimestamp(int(next(c for c in CALLS if c["method"] == "user.getrecenttracks")["from"]), TAIPEI)
    expected = (now.year * 12 + now.month - 1) - 5
    check("first sync starts 6 months back on the 1st (Taipei)",
          (first_from.year * 12 + first_from.month - 1) == expected and first_from.day == 1 and first_from.hour == 0)
    check("case variants merged into one song", r.text.count('name="listed_song"') == 2)
    check("now-playing skipped, placeholder art dropped", "2a96cbd8" not in r.text)

    ids = re.findall(r'name="listed_song" value="(\d+)"', r.text)
    keys = re.findall(r'name="listed_artist" value="([^"]+)"', r.text)
    alice.post("/me/music/review", data={"listed_artist": keys, "artist": keys, "listed_song": ids, "song": ids})
    page = anon.get("/u/alice").text
    check("profile ranks Last.fm songs", "DARE" in page and "BLOODY STREAM" in page and "2 次播放" in page)

    import sqlite3
    con = sqlite3.connect(db)
    months = dict(con.execute("SELECT month, SUM(plays) FROM monthlyplays GROUP BY month").fetchall())
    check("UTC->Taipei bucketing (Aug 31 17:00Z -> 2026-09)", months.get("2026-09") == 1 and "2026-08" not in months)
    con.close()

    # second sync: only from this month; same data again must not double count
    CALLS.clear()
    r = alice.post("/me/lastfm/sync")
    second_from = datetime.fromtimestamp(int(CALLS[0]["from"]), TAIPEI)
    check("re-sync starts at this month", second_from.strftime("%Y-%m") == this_month and second_from.day == 1)
    check("re-sync doesn't double count", "沒有新的歌曲" in r.text and "共 4 次播放" in r.text)

    # cross-source dedupe: same song from YouTube with more plays
    yt = [{"header": "YouTube Music", "title": "Watched DARE", "titleUrl": "https://music.youtube.com/watch?v=AAAAAAAAAA1",
           "subtitles": [{"name": "Gorillaz - Topic"}], "time": f"{this_month}-02T00:00:00Z"} for _ in range(5)]
    alice.post("/me/youtube/import", files={"history": ("watch-history.json", json.dumps(yt).encode(), "application/json")})
    r = alice.get("/me/music/review")
    ids = re.findall(r'name="listed_song" value="(\d+)"', r.text)
    keys = re.findall(r'name="listed_artist" value="([^"]+)"', r.text)
    alice.post("/me/music/review", data={"listed_artist": keys, "artist": keys, "listed_song": ids, "song": ids})
    page = anon.get("/u/alice").text
    music_panel = page.split('data-panel="music"')[1]
    songs_block = music_panel[music_panel.index("最常聽的歌曲"):]
    check("same song from 2 sources listed once with max plays", songs_block.count(">DARE<") == 1 and "5 次" in songs_block)
    artists_block = page[page.index("最常聽的歌手"):page.index("最常聽的歌曲")]
    check("artist plays use max across sources (5, not 5 + 2)", "5 次播放" in artists_block and "7 次播放" not in artists_block)
    r = alice.get("/me/collection")
    check("collection keeps both copies", r.text.count(">DARE<") == 2)

    # private profile
    SCENARIO["private"] = True
    r = alice.post("/me/lastfm/sync")
    check("hidden listening history -> privacy message", "隱藏了收聽紀錄" in r.text)
    SCENARIO["private"] = False

    # same Last.fm account (different case) on another user
    SCENARIO["username"] = "realfan"
    loc, cb = connect(bob)
    r = callback(bob, cb, "good-token")
    check("Last.fm account can't be linked twice", "已經連結到其他使用者" in r.text)

    # clearing Last.fm leaves YouTube data alone
    r = alice.post("/me/lastfm/clear")
    check("clear Last.fm removes only Last.fm songs", "已刪除 2 首從 Last.fm" in r.text and r.text.count(">DARE<") == 1)
    page = anon.get("/u/alice").text
    check("YouTube plays survive Last.fm clear", "5 次" in page[page.index("最常聽的歌曲"):])

    r = alice.post("/me/lastfm/unlink")
    check("unlink", "已解除 Last.fm 連結" in r.text and "連結 Last.fm" in r.text)

    settings.lastfm_shared_secret = ""
    r = alice.get("/me/lastfm/connect")
    check("missing shared secret -> clear message", "LASTFM_SHARED_SECRET" in r.text)

# Live: real Last.fm response shape (public account, last 60 days)
lastfm._call = real_call
try:
    s = asyncio.run(lastfm.get_scrobbles("rj", datetime.now(timezone.utc) - timedelta(days=365)))
    check(f"live: parsed {sum(s.plays.values())} scrobbles / {len(s.songs)} songs from a public account", True)
except lastfm.LastfmError as e:
    check(f"live call failed: {e}", False)
