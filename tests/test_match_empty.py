import os
import pathlib

here = pathlib.Path(__file__).parent
db = here / "test_match_empty.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, User, Work  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def add(username, titles):
    with Session(engine) as s:
        uid = s.exec(select(User).where(User.username == username)).one().id
        for t in titles:
            w = s.exec(select(Work).where(Work.title == t)).first()
            if w is None:
                w = Work(category=Category.anime, source="anilist", external_id=t, title=t)
                s.add(w)
                s.flush()
            s.add(CollectionEntry(user_id=uid, work_id=w.id, tier="great"))
        s.commit()


with TestClient(app):
    alice = client("alice")
    page = alice.get("/match").text
    check("few entries explained", "再多一點收藏就能開始配對" in page)

    add("alice", ["A", "B", "C"])
    page = alice.get("/match").text
    check("nobody else -> no_people message", "目前沒有新的人可以推薦" in page and "data-copy" in page)

    bob = client("bob")
    add("bob", ["X", "Y", "Z"])
    page = alice.get("/match").text
    check("others without overlap -> no_overlap message", "還沒找到和你有共同喜好的人" in page)

    alice.post("/friends/bob/request")
    page = alice.get("/match").text
    check("pending request excludes them -> no_people", "目前沒有新的人可以推薦" in page)

    carol = client("carol")
    add("carol", ["A", "B"])
    page = alice.get("/match").text
    check("overlap shows a card", 'data-user="carol"' in page and "目前沒有新的人" not in page)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
