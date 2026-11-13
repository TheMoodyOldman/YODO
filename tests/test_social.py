import json
import os
import pathlib
import re
import sqlite3
from datetime import datetime

db = pathlib.Path(__file__).parent / "test_social.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

import app.routers.me as me_router  # noqa: E402
import app.routers.work as work_router  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.main import app  # noqa: E402
from app.services import anilist, steam  # noqa: E402
from app.workinfo import WorkInfo  # noqa: E402

FAKE = {i: anilist.Anime(i, f"Show {i}", None, None, 2020, "TV") for i in range(1, 4)}
GAMES = {"v": []}


async def fake_get(i):
    return FAKE.get(i)


async def fake_owned(sid):
    return GAMES["v"]


async def fake_info(work):
    return WorkInfo()


me_router.anilist.get_anime = fake_get
steam.get_owned_games = fake_owned
work_router.get_work_info = fake_info


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


def feed_titles(client):
    return re.findall(r'<span class="card-title">([^<]+)</span>', client.get("/feed").text)


with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as carol, TestClient(app) as anon:
    for c, name in ((alice, "alice"), (bob, "bob"), (carol, "carol")):
        c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "display_name": name.title(), "password": "testpass123", "birth_date": "2000-01-01"})

    check("feed requires login", anon.get("/feed", follow_redirects=False).status_code == 303)
    check("empty feed explains how to add friends", "還沒有好友" in alice.get("/feed").text)

    # --- requests
    r = alice.get("/u/bob")
    check("stranger sees 加好友 + 封鎖", "＋ 加好友" in r.text and ">封鎖<" in r.text)
    check("logged-out visitor sees 登入後加好友", "登入後加好友" in anon.get("/u/bob").text)
    bob.post("/friends/alice/request", data={"next": "/u/alice"})
    check("requester sees pending state", "已送出邀請" in bob.get("/u/alice").text)
    r = alice.get("/feed")
    check("nav badge + feed banner for incoming request", 'class="nav-badge"' in r.text and "有 1 個好友邀請" in r.text)
    check("friends page lists incoming request", "好友邀請" in alice.get("/me/friends").text and "接受好友邀請" in alice.get("/me/friends").text)
    alice.post("/friends/bob/accept", data={"next": "/me/friends"})
    check("accepted: both see ✓ 好友", "✓ 好友" in alice.get("/u/bob").text and "✓ 好友" in bob.get("/u/alice").text)
    check("badge cleared", 'class="nav-badge"' not in alice.get("/feed").text)
    carol.post("/friends/alice/request")
    alice.post("/friends/carol/request")  # crossing requests = accept
    check("crossing requests become friends", "✓ 好友" in carol.get("/u/alice").text)
    alice.post("/friends/carol/decline")  # unfriend carol again
    check("unfriend removes friendship", "＋ 加好友" in carol.get("/u/alice").text)
    check("can't friend yourself", alice.post("/friends/alice/request").status_code == 404)

    # --- friends-only visibility
    alice.post("/me/settings", data={"display_name": "Alice", "visibility_game": "public", "visibility_anime": "friends", "visibility_music": "public"})
    alice.post("/me/collection/anime", data={"anilist_id": "1"})
    work1 = q("SELECT id FROM work WHERE title='Show 1'")[0][0]
    check("friend sees friends-only category", "Show 1" in bob.get("/u/alice").text and bob.get(f"/u/alice/w/{work1}").status_code == 200)
    check("non-friend doesn't", "Show 1" not in carol.get("/u/alice").text and carol.get(f"/u/alice/w/{work1}").status_code == 404)

    # --- feed: anime
    check("friend's new anime appears in feed", "Show 1" in feed_titles(bob))
    check("non-friend's feed doesn't show it", "Show 1" not in feed_titles(carol))
    check("own activity in own feed", "Show 1" in feed_titles(alice))
    entry1 = q("SELECT e.id FROM collectionentry e WHERE e.work_id=?", work1)[0][0]
    for tier in ("good", "great", "must_watch"):  # chip taps
        alice.post(f"/me/collection/{entry1}/verdict", data={"tier": tier, "tag": "神作"}, headers={"X-Requested-With": "fetch"})
    check("rating on add day doesn't add more items", q("SELECT COUNT(*) FROM activity")[0][0] == 1)
    check("feed shows current verdict", "此生必看</span>" in bob.get("/feed").text and "#神作" in bob.get("/feed").text)
    alice.post(f"/me/collection/{entry1}", data={"hidden": "true"})
    check("hidden entry drops out of feed", "Show 1" not in feed_titles(bob))
    alice.post(f"/me/collection/{entry1}", data={})

    # --- feed: games (only gains on reviewed games)
    q("UPDATE user SET steam_id='76561198000000001' WHERE username='alice'")
    GAMES["v"] = [steam.OwnedGame(413150, "Stardew Valley", 600, 300)]
    alice.post("/me/steam/sync")
    check("first sync (pending) makes no played item", "Stardew Valley" not in feed_titles(bob))
    r = alice.get("/me/steam/review")
    alice.post("/me/steam/review", data={"publish": re.findall(r'name="publish" value="(\d+)"', r.text)})
    GAMES["v"] = [steam.OwnedGame(413150, "Stardew Valley", 720, 420)]
    alice.post("/me/steam/sync")
    GAMES["v"] = [steam.OwnedGame(413150, "Stardew Valley", 780, 480)]
    alice.post("/me/steam/sync")
    r = bob.get("/feed")
    check("played item sums the day's gains", "Stardew Valley" in r.text and "玩了 <strong>3.0 小時</strong>" in r.text)

    # --- feed: music (this month's new plays)
    month = datetime.now(TAIPEI).strftime("%Y-%m")
    hist = [{"header": "YouTube Music", "title": "Watched Hit Song", "titleUrl": "https://music.youtube.com/watch?v=AAAAAAAAAA1",
             "subtitles": [{"name": "Band - Topic"}], "time": f"{month}-01T12:00:00Z"}] * 5 \
        + [{"header": "YouTube Music", "title": "Watched B Side", "titleUrl": "https://music.youtube.com/watch?v=BBBBBBBBBB2",
            "subtitles": [{"name": "Band - Topic"}], "time": f"{month}-01T12:00:00Z"}] * 2
    alice.post("/me/youtube/import", files={"history": ("watch-history.json", json.dumps(hist).encode(), "application/json")})
    check("listening hidden while songs await review", "Hit Song" not in feed_titles(bob))
    r = alice.get("/me/music/review")
    alice.post("/me/music/review", data={k: re.findall(rf'name="{k}" value="([^"]+)"', r.text) for k in ("listed_artist", "artist", "listed_song", "song")})
    r = bob.get("/feed")
    check("listened item: total plays + top song", "Hit Song" in r.text and "多聽了 <strong>7 次</strong>（2 首歌）" in r.text)
    alice.post("/me/youtube/import", files={"history": ("watch-history.json", json.dumps(hist).encode(), "application/json")})
    check("re-import adds no plays", "多聽了 <strong>7 次</strong>" in bob.get("/feed").text)

    # --- comments
    act = q("SELECT id FROM activity WHERE kind='anime_added'")[0][0]
    bob.post(f"/feed/{act}/comments", data={"body": "這部 <b>超讚</b>"})
    r = alice.get("/feed")
    check("comment shown, HTML escaped", "這部 &lt;b&gt;超讚&lt;/b&gt;" in r.text)
    check("non-friend can't comment", carol.post(f"/feed/{act}/comments", data={"body": "hi"}).status_code == 404)
    bob.post(f"/feed/{act}/comments", data={"body": "x" * 301})
    bob.post(f"/feed/{act}/comments", data={"body": "   "})
    check("too long / blank comments rejected", q("SELECT COUNT(*) FROM comment")[0][0] == 1)
    cid = q("SELECT id FROM comment")[0][0]
    check("others can't delete a comment", carol.post(f"/comments/{cid}/delete").status_code == 404)
    alice.post(f"/comments/{cid}/delete")
    check("activity owner can delete comments", q("SELECT COUNT(*) FROM comment")[0][0] == 0)

    # --- search
    r = carol.get("/me/friends", params={"q": "ALI"})
    check("search by name, case-insensitive", "@alice" in r.text and "＋ 加好友" in r.text)

    # --- blocking
    alice.post("/friends/bob/block")
    check("block removes friendship", "Show 1" not in feed_titles(bob))
    check("blocked can't see blocker's pages", bob.get("/u/alice").status_code == 404 and bob.get(f"/u/alice/w/{work1}").status_code == 404)
    check("blocker can't see blocked either", alice.get("/u/bob").status_code == 404)
    r = bob.post("/friends/alice/request")
    check("blocked user can't send requests", "無法送出好友邀請" in r.text and q("SELECT COUNT(*) FROM friendship WHERE requester_id=(SELECT id FROM user WHERE username='bob')")[0][0] == 0)
    check("blocked users hidden from search", "@alice" not in bob.get("/me/friends", params={"q": "ali"}).text)
    check("block list shown", "已封鎖" in alice.get("/me/friends").text)
    alice.post("/friends/bob/unblock")
    check("unblock restores profile access", bob.get("/u/alice").status_code == 200)
