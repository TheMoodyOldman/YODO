import json
import os
import pathlib
import re

here = pathlib.Path(__file__).parent
db = here / "test_tour.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": f"{name}@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def tour(page):
    m = re.search(r'<script id="tour-data" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else None


FETCH = {"X-Requested-With": "fetch"}

with TestClient(app):
    alice, bob = client("alice"), client("bob")

    data = tour(alice.get("/feed").text)
    check("new user is offered the tour", data is not None and data["state"] is None and len(data["steps"]) == 5)
    check("tour script loaded", "/static/js/tour.js" in alice.get("/feed").text)
    check("steps carry page, highlight targets and hints",
          all(s["href"] and s["targets"] and s["hint"] for s in data["steps"]))
    check("collect step shows progress", data["steps"][2]["progress"] == "已加入 0 / 3 個收藏")

    check("start", alice.post("/me/tour/start", headers=FETCH).json() == {"state": "active"})
    page = alice.get("/me/collection").text
    check("active tour data on every page", tour(page)["state"] == "active")
    check("checklist card steps aside while the tour runs", "開始使用 YODO" not in page)
    check("unknown action 404", alice.post("/me/tour/nope", headers=FETCH).status_code == 404)

    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "alice")).one()
        u.bio = "hello"
        s.add(u)
        s.commit()
    steps = tour(alice.get("/feed").text)["steps"]
    check("steps tick themselves off", [st["done"] for st in steps] == [False, True, False, False, False])

    alice.post("/me/tour/skip", headers=FETCH)
    page = alice.get("/feed").text
    check("skipped: no more tour", tour(page) is None and "tour.js" not in page)
    check("skipped: checklist card returns", "開始使用 YODO" in page)
    check("settings offers a restart", "重新開始互動教學" in alice.get("/me/settings").text)
    r = alice.post("/me/tour/start")
    check("restart from settings", tour(r.text)["state"] == "active")
    alice.post("/me/tour/finish", headers=FETCH)
    check("finished: no tour", tour(alice.get("/feed").text) is None)

    check("logged-out pages have no tour", tour(TestClient(app).get("/").text) is None)

    # 新加入的同好 on 探索 while there are no taste matches
    page = alice.get("/match").text
    check("newcomers listed when no matches", "新加入的同好" in page and 'data-tour="newcomer-add"' in page and "/friends/bob/request" in page)
    alice.post("/friends/bob/request")
    check("requested people leave the newcomer list", "/friends/bob/request" not in alice.get("/match").text)
    with Session(engine) as s:
        b = s.exec(select(User).where(User.username == "bob")).one()
        b.hide_from_match = True
        s.add(b)
        s.commit()
    carol = client("carol")
    check("people hidden from 探索 aren't newcomers", "/friends/bob/request" not in carol.get("/match").text)
    alice.post("/me/tour/start", headers=FETCH)
    steps = tour(alice.get("/feed").text)["steps"]
    check("a sent friend request completes the 同好 step", steps[3]["done"] is True)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
