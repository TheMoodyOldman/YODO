import asyncio
import json
import os
import pathlib
import re
from datetime import date

db = pathlib.Path(__file__).parent / "test_song.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import songquiz  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, Friendship, FriendStatus, GameRoom, User, Work  # noqa: E402
from app.services import itunes  # noqa: E402

LOOKUPS = []


async def fake_preview(artist, title):
    LOOKUPS.append(title)
    return None if title == "No Preview" else f"https://audio.test/{title.replace(' ', '_')}.m4a"


itunes.find_preview = fake_preview
from app.db import init_db  # noqa: E402

init_db()


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def room(code):
    with Session(engine) as s:
        r = s.exec(select(GameRoom).where(GameRoom.code == code)).one()
        return r.status, json.loads(r.state)


with Session(engine) as s:
    users = {n: User(username=n, display_name=n.title(), password_hash=hash_password("testpass123"), birth_date=date(2000, 1, 1))
             for n in ("alice", "bob", "carol", "dave")}
    s.add_all(users.values())
    s.flush()

    def song(title, artist, src="youtube"):
        w = Work(category=Category.music, source=src, external_id=title.replace(" ", "")[:11].ljust(11, "x"), title=title, creator=artist)
        s.add(w)
        s.flush()
        return w

    shared = [song(f"Shared {i}", "Band S") for i in range(4)] + [song("No Preview", "Band S")]
    lastfm_copy = song("Shared 0", "Band S", "lastfm")  # same song via Last.fm for bob
    alice_only = [song(f"Alice Only {i}", "Solo A") for i in range(12)]
    bob_artist = song("Bob Deep Cut", "Band S")  # shared artist, only bob has the song
    carol_only = song("Carol Secret", "Solo C")
    for w in shared:
        s.add(CollectionEntry(user_id=users["alice"].id, work_id=w.id, play_count=20))
        if w.title != "Shared 0":
            s.add(CollectionEntry(user_id=users["bob"].id, work_id=w.id, play_count=10))
    s.add(CollectionEntry(user_id=users["bob"].id, work_id=lastfm_copy.id, play_count=30))
    s.add(CollectionEntry(user_id=users["bob"].id, work_id=bob_artist.id, play_count=5))
    for w in alice_only:
        s.add(CollectionEntry(user_id=users["alice"].id, work_id=w.id, play_count=1))
    s.add(CollectionEntry(user_id=users["carol"].id, work_id=carol_only.id, play_count=99))
    s.add(Friendship(requester_id=users["alice"].id, addressee_id=users["bob"].id, status=FriendStatus.accepted))
    s.commit()
    uid = {n: u.id for n, u in users.items()}

with Session(engine) as s:
    a, b = s.get(User, uid["alice"]), s.get(User, uid["bob"])
    quiz = asyncio.run(songquiz.build_quiz(s, a, b, True))
    titles = [r["t"] for r in quiz]
    check("5 songs from shared ground when there is enough of it", len(quiz) == 5 and not any(t.startswith(("Alice Only", "Carol")) for t in titles))
    check("shared songs first (cross-source match counts), then shared artist",
          set(titles) == {"Shared 0", "Shared 1", "Shared 2", "Shared 3", "Bob Deep Cut"} and quiz[0]["tier"] == 0)
    check("song without a preview skipped", "No Preview" not in titles)
    check("16 options with unique titles incl. the answer", all(len(r["o"]) == 16 and r["id"] in {o["id"] for o in r["o"]}
                                                               and len({o["t"].casefold() for o in r["o"]}) == 16 for r in quiz))
    shared0 = next(r for r in quiz if r["t"] == "Shared 0")
    check("YouTube copy preferred for the reveal embed", shared0["yt"] is not None)
    n = len(LOOKUPS)
    asyncio.run(songquiz.build_quiz(s, a, b, True))
    check("previews cached on the work (no repeat lookups)", len(LOOKUPS) == n)
    c, d = s.get(User, uid["carol"]), s.get(User, uid["dave"])
    try:
        asyncio.run(songquiz.build_quiz(s, c, d, False))
        check("no common ground -> NotEnoughSongs", False)
    except songquiz.NotEnoughSongs:
        check("too few songs with previews in both libraries -> NotEnoughSongs", True)
    quiz = asyncio.run(songquiz.build_quiz(s, a, d, False))  # dave has no music at all
    check("no shared songs: falls back to songs only one player has, labelled",
          len(quiz) == 5 and all(r["own"] == [a.display_name] for r in quiz)
          and {r["why"] for r in quiz} <= {"只有一人聽過", "熱門歌曲"})

A, B, C = TestClient(app), TestClient(app), TestClient(app)
for cl, n in ((A, "alice"), (B, "bob"), (C, "carol")):
    cl.__enter__()
    cl.post("/login", data={"username": n, "password": "testpass123"})

check("hub lists 猜歌對戰", 'href="/games/song"' in A.get("/games").text)
code = A.post("/games/song/new", follow_redirects=False).headers["location"].rsplit("/", 1)[1]
check("can't start alone", "要兩個人" in A.post(f"/games/song/{code}/start").text)
B.get(f"/games/song/{code}")
check("third player refused", "已經滿了" in C.get(f"/games/song/{code}").text)
check("guest can't start", B.post(f"/games/song/{code}/start", follow_redirects=False).status_code == 403)
A.post(f"/games/song/{code}/start")
status, st = room(code)
check("started", status == "playing" and st["phase"] == "play" and st["stage"] == 0)
r0 = st["rounds"][0]
page = A.get(f"/games/song/{code}").text
check("play page has the clip, not the answer reveal", r0["p"] in page and "首答案" not in page and "youtube" not in page)
check("outsider can't act", C.post(f"/games/song/{code}/guess", data={"choice": r0["id"]}).status_code == 403)

wrong = next(o["id"] for o in r0["o"] if o["id"] != r0["id"])
A.post(f"/games/song/{code}/guess", data={"choice": wrong})
A.post(f"/games/song/{code}/guess", data={"choice": r0["id"]})
_, st = room(code)
check("one guess per stage", st["scores"][str(uid["alice"])] == 0 and st["stage"] == 0)
check("wrong option greyed for that player", "song-option wrong" in A.get(f"/games/song/{code}").text)
B.post(f"/games/song/{code}/pass")
_, st = room(code)
check("stage advances only after both acted", st["stage"] == 1)
A.post(f"/games/song/{code}/guess", data={"choice": wrong})
_, st = room(code)
check("can't re-pick an option already wrong", str(uid["alice"]) not in st["acted"])
A.post(f"/games/song/{code}/guess", data={"choice": r0["id"]})
B.post(f"/games/song/{code}/guess", data={"choice": r0["id"]})
_, st = room(code)
check("stage-2 correct = 4 points each, reveal", st["phase"] == "reveal" and st["scores"][str(uid["alice"])] == 4 and st["scores"][str(uid["bob"])] == 4)
page = A.get(f"/games/song/{code}").text
check("reveal shows answer + YouTube (embed or link)", r0["t"] in page and ("youtube-nocookie.com/embed/" in page or "youtube.com/results" in page))
A.post(f"/games/song/{code}/next")
check("next waits for both", room(code)[1]["i"] == 0)
B.post(f"/games/song/{code}/next")
_, st = room(code)
check("round 2 starts fresh", st["i"] == 1 and st["stage"] == 0 and st["acted"] == {} and st["solved"] == {})

# Round 2: nobody guesses -> passes through all stages to reveal
for _ in songquiz.STAGES:
    A.post(f"/games/song/{code}/pass")
    B.post(f"/games/song/{code}/pass")
_, st = room(code)
check("unsolved after the 30 s stage -> reveal, 0 points", st["phase"] == "reveal" and st["scores"][str(uid["alice"])] == 4)
for _ in range(3):  # finish: bob gets the rest at the first stage
    A.post(f"/games/song/{code}/next"); B.post(f"/games/song/{code}/next")
    _, st = room(code)
    if st["phase"] == "done":
        break
    rnd = st["rounds"][st["i"]]
    B.post(f"/games/song/{code}/guess", data={"choice": rnd["id"]})
    A.post(f"/games/song/{code}/pass")
    for _ in range(4):
        A.post(f"/games/song/{code}/pass")
A.post(f"/games/song/{code}/next"); B.post(f"/games/song/{code}/next")
status, st = room(code)
page = A.get(f"/games/song/{code}").text
check("after 5 songs: done, winner announced", status == "done" and "Bob 獲勝" in page and st["scores"][str(uid["bob"])] == 4 + 15)
check("final list links every song", page.count("完整聆聽") == 5)
for cl in (A, B, C):
    cl.__exit__(None, None, None)
