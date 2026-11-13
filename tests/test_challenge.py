import io
import os
import pathlib
from datetime import date, timedelta

db = pathlib.Path(__file__).parent / "test_challenge.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

import app.routers.games as games_router  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Challenge, CollectionEntry, Friendship, FriendStatus, User, Work  # noqa: E402


async def no_images(urls):
    return {}


games_router.fetch_images = no_images
FETCH = {"X-Requested-With": "fetch"}


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def jpeg_ok(resp):
    try:
        return resp.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(resp.content)).size == (1080, 1920)
    except Exception:
        return False


with TestClient(app) as alice, TestClient(app) as bob:
    with Session(engine) as s:
        a = User(username="alice", display_name="Alice", password_hash=hash_password("testpass123"), birth_date=date(2000, 1, 1))
        b = User(username="bob", display_name="Bob", password_hash=hash_password("testpass123"), birth_date=date(2000, 1, 1))
        s.add_all([a, b])
        s.flush()
        works = {t: Work(category=c, source="test", external_id=t, title=t, creator=cr) for t, c, cr in [
            ("Frieren", Category.anime, None), ("Bocchi", Category.anime, None), ("Pending Show", Category.anime, None),
            ("Not Mine", Category.anime, None), ("Stardew", Category.game, None), ("Summer Song", Category.music, "Band A"),
        ]}
        s.add_all(works.values())
        s.flush()
        for t in ("Frieren", "Bocchi", "Stardew", "Summer Song"):
            s.add(CollectionEntry(user_id=a.id, work_id=works[t].id, play_count=5 if t == "Summer Song" else None))
        s.add(CollectionEntry(user_id=a.id, work_id=works["Pending Show"].id, pending_review=True))
        s.add(CollectionEntry(user_id=b.id, work_id=works["Not Mine"].id))
        s.add(Friendship(requester_id=a.id, addressee_id=b.id, status=FriendStatus.accepted))
        s.commit()
        wid = {t: w.id for t, w in works.items()}

    alice.post("/login", data={"username": "alice", "password": "testpass123"})
    bob.post("/login", data={"username": "bob", "password": "testpass123"})

    check("hub lists 30 天挑戰", 'href="/games/challenge"' in alice.get("/games").text)
    r = alice.get("/games/challenge/anime")
    check("not started -> start button", "開始第 1 天" in r.text)
    check("unknown kind 404", alice.get("/games/challenge/books").status_code == 404)
    alice.post("/games/challenge/anime/start")
    r = alice.get("/games/challenge/anime")
    check("day 1 unlocked, day 2 locked", 'data-day="1" data-prompt="入坑的第一部動畫"' in r.text and r.text.count("disabled aria-disabled") == 29)

    r = alice.post("/games/challenge/anime/pick", data={"day": 1, "work_id": wid["Frieren"]}, headers=FETCH)
    check("pick day 1 from own collection", r.status_code == 200 and r.json()["title"] == "Frieren")
    check("future day refused", alice.post("/games/challenge/anime/pick", data={"day": 2, "work_id": wid["Bocchi"]}).status_code == 400)
    for bad, why in (("Not Mine", "someone else's"), ("Stardew", "wrong category"), ("Pending Show", "awaiting review")):
        check(f"refuse {why} work", alice.post("/games/challenge/anime/pick", data={"day": 1, "work_id": wid[bad]}).status_code == 400)

    opts = alice.get("/games/challenge/anime/options", params={"q": "boc"}).json()
    check("search own anime by title", [o["title"] for o in opts] == ["Bocchi"])
    all_opts = {o["title"] for o in alice.get("/games/challenge/anime/options").json()}
    check("options exclude others' and pending works", all_opts == {"Frieren", "Bocchi"})
    alice.post("/games/challenge/music/start")
    check("music search matches artist", [o["title"] for o in alice.get("/games/challenge/music/options", params={"q": "band a"}).json()] == ["Summer Song"])

    with Session(engine) as s:  # pretend alice started 9 days ago
        ch = s.exec(select(Challenge).where(Challenge.kind == "anime")).one()
        ch.started_on = date.today() - timedelta(days=9)
        s.add(ch)
        s.commit()
    check("day 10 unlocked after 9 days", alice.post("/games/challenge/anime/pick", data={"day": 10, "work_id": wid["Bocchi"]}, headers=FETCH).status_code == 200)
    check("day 11 still locked", alice.post("/games/challenge/anime/pick", data={"day": 11, "work_id": wid["Bocchi"]}).status_code == 400)
    r = alice.get("/games/challenge/anime")
    check("board shows 2 / 30 and latest day share", "<strong>2</strong> / 30" in r.text and "Day 10 限動" in r.text)
    check("index shows progress", "已完成 2 / 30 天" in alice.get("/games/challenge").text)

    feed = bob.get("/feed").text
    check("friend's feed shows the pick", "30 天動畫挑戰 Day 10：看過兩次以上的一部" in feed and "Bocchi" in feed)

    check("grid card JPEG", jpeg_ok(alice.get("/games/challenge/anime/card.jpg")))
    check("day card JPEG", jpeg_ok(alice.get("/games/challenge/anime/day/10.jpg")))
    check("unpicked day card 404", alice.get("/games/challenge/anime/day/5.jpg").status_code == 404)
    check("other users can't render alice's cards", bob.get("/games/challenge/anime/day/10.jpg").status_code == 404)

    alice.post("/games/challenge/anime/pick", data={"day": 10, "work_id": 0}, headers=FETCH)
    check("clear a day", "<strong>1</strong> / 30" in alice.get("/games/challenge/anime").text)
    alice.post("/games/challenge/anime/start", data={"restart": "true"})
    r = alice.get("/games/challenge/anime")
    check("restart clears picks and resets to day 1", "<strong>0</strong> / 30 天</span>" in r.text and "已解鎖 1 天" in r.text)
    check("challenge share event accepted",
          alice.post("/me/card/events", json={"period": "challenge", "key": "anime-1", "action": "share"}).status_code == 204)
