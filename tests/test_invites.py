import os
import pathlib

here = pathlib.Path(__file__).parent
db = here / "test_invites.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": f"{name}@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


FETCH = {"X-Requested-With": "fetch"}

with TestClient(app):
    alice, bob, carol, dave = (client(n) for n in ("alice", "bob", "carol", "dave"))
    for a, b, an, bn in ((alice, bob, "alice", "bob"), (alice, dave, "alice", "dave")):
        a.post(f"/friends/{bn}/request")
        b.post(f"/friends/{an}/accept")

    code = alice.post("/games/song/new", follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    lobby = alice.get(f"/games/song/{code}").text
    check("lobby lists friends to invite", "邀請好友" in lobby and f"/invite/bob" in lobby and f"/invite/dave" in lobby)
    check("non-friends aren't listed", "/invite/carol" not in lobby)
    check("invite script on every page", "/static/js/invites.js" in bob.get("/feed").text)

    r = alice.post(f"/games/room/song/{code}/invite/bob", headers=FETCH)
    check("invite a friend", r.json() == {"ok": True})
    inv = bob.get("/games/invites").json()["invites"]
    check("friend sees the invite", len(inv) == 1 and inv[0]["from"] == "alice" and inv[0]["game"] == "猜歌對戰"
          and inv[0]["url"] == f"/games/song/{code}")
    check("lobby marks invited friends", "再邀一次" in alice.get(f"/games/song/{code}").text)
    check("can't invite non-friends", alice.post(f"/games/room/song/{code}/invite/carol", headers=FETCH).status_code == 400)
    check("can't invite unknown users", alice.post(f"/games/room/song/{code}/invite/nobody", headers=FETCH).status_code == 400)
    check("others have no invites", carol.get("/games/invites").json()["invites"] == [])

    bob.post(f"/games/invites/{inv[0]['id']}/decline")
    check("declined invite disappears", bob.get("/games/invites").json()["invites"] == [])
    check("can't decline others' invites", carol.post(f"/games/invites/{inv[0]['id']}/decline").status_code == 404)
    alice.post(f"/games/room/song/{code}/invite/bob", headers=FETCH)
    check("inviting again brings it back", len(bob.get("/games/invites").json()["invites"]) == 1)

    alice.post(f"/games/room/song/{code}/invite/dave", headers=FETCH)
    bob.get(f"/games/song/{code}")  # joins: room now full (2 players)
    check("joined player no longer sees it", bob.get("/games/invites").json()["invites"] == [])
    check("full room: other invites vanish", dave.get("/games/invites").json()["invites"] == [])
    check("full room: no more inviting", "邀請好友" not in alice.get(f"/games/song/{code}").text
          and alice.post(f"/games/room/song/{code}/invite/dave", headers=FETCH).status_code == 400)

    # undercover allows more people
    ucode = alice.post("/games/undercover/new", follow_redirects=False).headers["location"].rsplit("/", 1)[1]
    alice.post(f"/games/room/undercover/{ucode}/invite/dave", headers=FETCH)
    inv = dave.get("/games/invites").json()["invites"]
    check("undercover invite", len(inv) == 1 and inv[0]["game"] == "猜誰是臥底")
    dave.post("/friends/alice/block")
    check("blocking hides their invites", dave.get("/games/invites").json()["invites"] == [])
    check("outsiders can't invite into a room they're not in",
          bob.post(f"/games/room/undercover/{ucode}/invite/alice", headers=FETCH).status_code == 400)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
