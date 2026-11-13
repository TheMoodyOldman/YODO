import json
import os
import pathlib
import re
from datetime import date

db = pathlib.Path(__file__).parent / "test_uc.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, GameRoom, User, Work  # noqa: E402
from app.services import anilist  # noqa: E402

CASTS = {
    1: [(f"芙莉蓮{i}", f"Frieren {i}") for i in range(10)],
    2: [(f"波奇{i}", f"Bocchi {i}") for i in range(10)],
}
MODE = {"chars": True}


async def fake_chars(i):
    return CASTS.get(i, []) if MODE["chars"] else []


anilist.get_characters = fake_chars
NAMES = ["alice", "bob", "carol", "dave", "eve", "zed"]


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def room_state(code):
    with Session(engine) as s:
        r = s.exec(select(GameRoom).where(GameRoom.code == code)).one()
        return r.status, json.loads(r.state)


clients = {n: TestClient(app) for n in NAMES}
for c in clients.values():
    c.__enter__()
with Session(engine) as s:
    users = {}
    for n in NAMES:
        users[n] = User(username=n, display_name=n.title(), password_hash=hash_password("testpass123"), birth_date=date(2000, 1, 1))
        s.add(users[n])
    s.flush()
    works = [Work(category=Category.anime, source="anilist", external_id=str(i), title=f"Show {i}") for i in (1, 2)]
    works += [Work(category=Category.anime, source="test", external_id=f"t{i}", title=f"Title {i}") for i in range(20)]
    s.add_all(works)
    s.flush()
    for n in NAMES:
        for w in works:
            s.add(CollectionEntry(user_id=users[n].id, work_id=w.id))
    s.commit()
    uid = {n: u.id for n, u in users.items()}
for n, c in clients.items():
    c.post("/login", data={"username": n, "password": "testpass123"})
A, B, C, D, E = (clients[n] for n in NAMES[:5])

check("hub lists 猜誰是臥底", 'href="/games/undercover"' in A.get("/games").text)
r = A.post("/games/undercover/new", data={"theme": "characters"}, follow_redirects=False)
code = r.headers["location"].rsplit("/", 1)[1]
check("room created with a 6-char code", len(code) == 6)
B.get(f"/games/undercover/{code}")
r = B.post(f"/games/undercover/{code}/start", follow_redirects=False)
check("non-host can't start", r.status_code == 403)
r = A.post(f"/games/undercover/{code}/start")
check("needs 3 players", "至少要 3 個人" in r.text)
for c in (C, D):
    c.get(f"/games/undercover/{code}")
lobby = A.get(f"/games/undercover/{code}").text
check("lobby lists 4 players", lobby.count("<li>") >= 4 and all(n.title() in lobby for n in ("Alice", "Bob", "Carol", "Dave")))
v1 = A.get(f"/games/room/undercover/{code}/v").json()["v"]

A.post(f"/games/undercover/{code}/start")
status, st = room_state(code)
check("started: describe phase, 16 cells, A/B from the same show", status == "describe" and len(st["grid"]) == 16
      and st["grid"][st["a"]]["t"][:2] == st["grid"][st["b"]]["t"][:2])
check("version changed after start", A.get(f"/games/room/undercover/{code}/v").json()["v"] != v1)
check("late joiner refused", "這局已經開始" in E.get(f"/games/undercover/{code}").text)
spy = st["spy"]
name_of = {v: k for k, v in uid.items()}
pages = {n: clients[n].get(f"/games/undercover/{code}").text for n in ("alice", "bob", "carol", "dave")}
mine_ok = all(
    len(re.findall(r'class="uc-cell mine"', html)) == 1
    and re.findall(r'<div class="uc-cell mine">\s*<span>([^<]+)</span>', html)[0] == st["grid"][st["b"] if uid[n] == spy else st["a"]]["t"]
    for n, html in pages.items()
)
check("everyone sees exactly their own word circled (spy gets B)", mine_ok)
check("nobody is told who the spy is", all("臥底</span>" not in h and "word-a" not in h for h in pages.values()))

order = st["order"]
r = clients[name_of[order[1]]].post(f"/games/undercover/{code}/describe", data={"text": "插隊"})
check("out-of-turn description ignored", room_state(code)[1]["turn"] == 0)
for i, u in enumerate(order):
    clients[name_of[u]].post(f"/games/undercover/{code}/describe", data={"text": f"描述{i}" if i % 2 == 0 else ""})
status, st = room_state(code)
check("after everyone speaks -> vote", status == "vote" and st["descs"][str(order[1])] == "")

civilians = [u for u in order if u != spy]
clients[name_of[civilians[0]]].post(f"/games/undercover/{code}/vote", data={"target": civilians[0]})
check("self-vote ignored", room_state(code)[1]["votes"] == {})
check("outsider can't vote", E.post(f"/games/undercover/{code}/vote", data={"target": spy}).status_code == 403)
for u in order:
    clients[name_of[u]].post(f"/games/undercover/{code}/vote", data={"target": spy if u != spy else civilians[0]})
status, st = room_state(code)
check("spy caught -> spy guesses", status == "guess" and st["accused"] == spy)
check("civilian can't guess", clients[name_of[civilians[0]]].post(f"/games/undercover/{code}/guess", data={"index": st["a"]}) and room_state(code)[0] == "guess")
clients[name_of[spy]].post(f"/games/undercover/{code}/guess", data={"index": st["a"]})
status, st = room_state(code)
done_page = A.get(f"/games/undercover/{code}").text
check("correct guess = tie, words revealed", status == "done" and st["result"] == "tie" and "平手" in done_page and "word-a" in done_page)

# Round 2: wrong guess -> civilians win
A.post(f"/games/undercover/{code}/start")
status, st = room_state(code)
spy, order = st["spy"], st["order"]
for u in order:
    clients[name_of[u]].post(f"/games/undercover/{code}/describe", data={"text": ""})
others = [u for u in order if u != spy]
for u in order:
    clients[name_of[u]].post(f"/games/undercover/{code}/vote", data={"target": spy if u != spy else others[0]})
wrong = next(i for i in range(16) if i not in (st["a"], st["b"]))
clients[name_of[spy]].post(f"/games/undercover/{code}/guess", data={"index": wrong})
check("wrong guess = civilians win", room_state(code)[1]["result"] == "civilians")

# Round 3: wrong person voted out -> spy wins
A.post(f"/games/undercover/{code}/start")
status, st = room_state(code)
spy, order = st["spy"], st["order"]
for u in order:
    clients[name_of[u]].post(f"/games/undercover/{code}/describe", data={"text": ""})
scapegoat = next(u for u in order if u != spy)
for u in order:
    clients[name_of[u]].post(f"/games/undercover/{code}/vote", data={"target": scapegoat if u != scapegoat else spy})
status, st = room_state(code)
check("wrong person accused = spy wins", status == "done" and st["result"] == "spy")

# Fallback: no characters available -> anime titles
MODE["chars"] = False
r = A.post("/games/undercover/new", data={"theme": "characters"}, follow_redirects=False)
code2 = r.headers["location"].rsplit("/", 1)[1]
for c in (B, C):
    c.get(f"/games/undercover/{code2}")
A.post(f"/games/undercover/{code2}/start")
status, st = room_state(code2)
check("falls back to anime titles", status == "describe" and st["theme"] == "anime" and all(c["t"].startswith(("Show", "Title")) for c in st["grid"]))
check("unknown room -> back to lobby page", "找不到這個房間" in A.get("/games/undercover/ZZZZZZ").text)
for c in clients.values():
    c.__exit__(None, None, None)
