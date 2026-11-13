import os
import pathlib
import re

db = pathlib.Path(__file__).parent / "test.db"
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


with TestClient(app) as alice, TestClient(app) as anon:
    # auth
    r = alice.get("/me/collection", follow_redirects=False)
    check("login required redirects", r.status_code == 303 and r.headers["location"].startswith("/login?next="))
    r = alice.post("/register", data={"username": "AB", "email": str("AB").lower() + "@test.yodo", "password": "12345678", "birth_date": "2000-01-01"})
    check("bad username rejected", r.status_code == 400 and "帳號需為" in r.text)
    r = alice.post("/register", data={"username": "alice_01", "email": str("alice_01").lower() + "@test.yodo", "display_name": "Alice", "password": "short", "birth_date": "2000-01-01"})
    check("short password rejected", r.status_code == 400)
    r = alice.post("/register", data={"username": "Alice_01", "email": str("Alice_01").lower() + "@test.yodo", "display_name": "Alice", "password": "testpass123", "birth_date": "2000-01-01"})
    check("register ok -> collection", r.status_code == 200 and "我的收藏" in r.text and str(r.url).endswith("/me/collection"))
    r = anon.post("/register", data={"username": "alice_01", "email": str("alice_01").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    check("duplicate username rejected", r.status_code == 400)
    r = anon.post("/login", data={"username": "alice_01", "password": "wrongpass1"})
    check("wrong password rejected", r.status_code == 400)
    r = anon.post("/login", data={"username": "alice_01", "password": "testpass123", "next": "//evil.com"}, follow_redirects=False)
    check("login ok, open redirect blocked", r.status_code == 303 and r.headers["location"] == "/me/collection")
    anon.post("/logout")

    # search & add (real AniList call)
    r = alice.get("/me/collection", params={"q": "Frieren"})
    ids = re.findall(r'name="anilist_id" value="(\d+)"', r.text)
    check(f"AniList search returns results ({len(ids)})", r.status_code == 200 and len(ids) > 0)
    r = alice.post("/me/collection/anime", data={"anilist_id": ids[0], "q": "Frieren"})
    check("add anime", r.status_code == 200 and "已加入《" in r.text)
    alice.post("/me/collection/anime", data={"anilist_id": ids[0]})
    r = alice.get("/me/collection")
    entry_ids = re.findall(r'id="entry-(\d+)"', r.text)
    check("adding twice keeps one entry", len(entry_ids) == 1)
    r = alice.get("/me/collection", params={"q": "Frieren"})
    check("search marks already-added", "已加入</span>" in r.text)

    r = alice.get("/me/collection", params={"q": "Bocchi the Rock"})
    second = re.findall(r'name="anilist_id" value="(\d+)"', r.text)[0]
    alice.post("/me/collection/anime", data={"anilist_id": second})
    entry_ids = re.findall(r'id="entry-(\d+)"', alice.get("/me/collection").text)

    # rate + hide
    alice.post(f"/me/collection/{entry_ids[0]}/verdict", data={"tier": "great", "tag": "胃痛"})
    alice.post(f"/me/collection/{entry_ids[1]}", data={"rating": "", "hidden": "true"})
    page = anon.get("/u/alice_01").text
    check("public profile shows anime verdict", "大推</span>" in page and "#胃痛" in page)
    check("hidden entry not on profile", len(re.findall(r'class="card(?: extra)?"', page.split('data-panel="anime"')[1])) == 1)
    check("og tags present", 'property="og:title"' in page)

    # privacy
    r = anon.get("/u/alice_01")
    check("anon sees anime section", "<h2>" in r.text and "動畫" in r.text and "還沒有公開任何收藏" not in r.text)
    alice.post("/me/settings", data={"display_name": "Alice W", "bio": "hello", "visibility_game": "public",
                                     "visibility_anime": "private", "visibility_music": "friends"})
    r = anon.get("/u/alice_01")
    check("private category hidden from anon", "還沒有公開任何收藏" in r.text and 'class="card"' not in r.text)
    r = alice.get("/u/alice_01")
    check("owner still sees private category", 'class="card"' in r.text and "僅自己" in r.text)
    check("settings saved", "Alice W" in r.text and "hello" in r.text)

    # ownership & delete
    anon.post("/register", data={"username": "bob", "email": str("bob").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    r = anon.post(f"/me/collection/{entry_ids[0]}/delete", follow_redirects=False)
    check("cannot delete someone else's entry", r.status_code == 404)
    anon.post("/logout")
    r = alice.post(f"/me/collection/{entry_ids[0]}/delete")
    check("delete own entry", "已從收藏移除" in r.text and len(re.findall(r'id="entry-', r.text)) == 1)

    check("unknown user -> 404 page", anon.get("/u/nobody").status_code == 404)

try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
