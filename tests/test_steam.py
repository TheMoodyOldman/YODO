import asyncio
import os
import pathlib
import re
from urllib.parse import parse_qs, urlparse

db = pathlib.Path(__file__).parent / "test_steam.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import steam  # noqa: E402

STEAM_ID = "76561198000000001"
GAMES = {"value": []}


async def fake_owned(steam_id):
    return GAMES["value"]


async def fake_verify(params):
    m = re.search(r"(\d{17})$", params.get("openid.claimed_id", ""))
    return m.group(1) if m else None


real_verify = steam.verify_openid
steam.get_owned_games = fake_owned
steam.verify_openid = fake_verify


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def start_connect(client):
    r = client.get("/me/steam/connect", follow_redirects=False)
    loc = r.headers["location"]
    q = parse_qs(urlparse(loc).query)
    return loc, q["openid.return_to"][0]


def openid_params(return_to, steam_id=STEAM_ID):
    state = parse_qs(urlparse(return_to).query).get("state", [""])[0]
    return {
        "state": state,
        "openid.mode": "id_res",
        "openid.op_endpoint": steam.OPENID_URL,
        "openid.claimed_id": f"https://steamcommunity.com/openid/id/{steam_id}",
        "openid.identity": f"https://steamcommunity.com/openid/id/{steam_id}",
        "openid.return_to": return_to,
    }


with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    bob.post("/register", data={"username": "bob", "email": str("bob").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})

    loc, return_to = start_connect(alice)
    check("connect redirects to Steam OpenID", loc.startswith(steam.OPENID_URL))
    state = parse_qs(urlparse(return_to).query)["state"][0]

    # tampered state
    bad = return_to.replace(state, "forged")
    r = alice.get(bad, params={**openid_params(bad), "state": "forged"})
    check("forged state rejected", "已失效" in r.text and STEAM_ID not in r.text)

    # state consumed; start again; mismatched return_to
    loc, return_to = start_connect(alice)
    params = {**openid_params("http://evil.example/cb"), "state": parse_qs(urlparse(return_to).query)["state"][0]}
    r = alice.get(return_to, params=params)
    check("mismatched return_to rejected", "驗證失敗" in r.text)

    # valid link + first sync
    GAMES["value"] = [
        steam.OwnedGame(413150, "Stardew Valley", 12000),
        steam.OwnedGame(570, "Dota 2", 30),
        steam.OwnedGame(1145360, "Hades", 600),
    ]
    loc, return_to = start_connect(alice)
    r = alice.get(return_to, params=openid_params(return_to))
    check("link -> review page", str(r.url).endswith("/me/steam/review") and "找到 2 款新遊戲" in r.text)
    check("short-playtime game skipped", "Dota 2" not in r.text)
    check("review sorted by playtime", r.text.index("Stardew") < r.text.index("Hades"))
    ids = re.findall(r'name="publish" value="(\d+)"', r.text)

    page = anon.get("/u/alice").text
    check("pending games not public yet", "Stardew" not in page)
    r = alice.get("/me/collection")
    check("collection shows pending banner", "有 2 款從 Steam 匯入" in r.text)

    r = alice.post("/me/steam/review", data={"publish": [ids[0]]})
    check("review submitted", "已公開 1 款遊戲" in r.text)
    page = anon.get("/u/alice").text
    check("published game on profile with hours", "Stardew Valley" in page and "200 小時" in page)
    check("unchecked game hidden", "Hades" not in page)

    # resync: playtime change + new game
    GAMES["value"] = [
        steam.OwnedGame(413150, "Stardew Valley", 12600),
        steam.OwnedGame(1145360, "Hades", 660),
        steam.OwnedGame(367520, "Hollow Knight", 3000),
    ]
    r = alice.post("/me/steam/sync")
    check("resync -> review only new game", "找到 1 款新遊戲" in r.text and "Hollow Knight" in r.text and "Hades" not in r.text)
    alice.post("/me/steam/review", data={"publish": re.findall(r'name="publish" value="(\d+)"', r.text)})
    page = anon.get("/u/alice").text
    check("playtime updated", "210 小時" in page)
    check("previously hidden game stays hidden", "Hades" not in page)
    check("profile ordered by playtime", page.index("Stardew") < page.index("Hollow Knight"))

    r = alice.post("/me/steam/sync")
    check("no-change sync message", "沒有新的遊戲" in r.text)

    # private profile
    GAMES["value"] = None
    r = alice.post("/me/steam/sync")
    check("private profile message", "不是公開的" in r.text)

    # same steam account on another user
    loc, return_to = start_connect(bob)
    r = bob.get(return_to, params=openid_params(return_to))
    check("steam id can't be linked twice", "已經連結到其他使用者" in r.text)

    r = alice.post("/me/steam/unlink")
    check("unlink keeps games", "已解除" in r.text and "Stardew Valley" in r.text)

# Live: Steam must reject an unsigned/forged assertion
forged = openid_params("http://localhost/me/steam/callback?state=x")
forged.update({"openid.ns": "http://specs.openid.net/auth/2.0", "openid.response_nonce": "2026-10-09T00:00:00Zabc",
               "openid.assoc_handle": "1234567890", "openid.signed": "signed,op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
               "openid.sig": "AAAAAAAAAAAAAAAAAAAAAAAAAAA="})
check("live: Steam rejects forged OpenID assertion", asyncio.run(real_verify(forged)) is None)
