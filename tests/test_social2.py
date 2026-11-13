import os
import pathlib
import re
from datetime import timedelta

here = pathlib.Path(__file__).parent
db = here / "test_social2.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import nearby  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, Message, NearbyPost, User, Work, utcnow  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def befriend(a, b, a_name, b_name):
    a.post(f"/friends/{b_name}/request")
    b.post(f"/friends/{a_name}/accept")


SETTINGS = {"display_name": "", "bio": "", "region": "", **{f"visibility_{c.value}": "public" for c in Category}, "show_in_match": "1"}

with TestClient(app):
    alice, bob, carol, dave = (client(n) for n in ("alice", "bob", "carol", "dave"))
    anon = TestClient(app)

    # ---------- 聯絡方式 ----------
    r = alice.post("/me/settings", data={**SETTINGS, "display_name": "Alice", "contact_line": "alice_line",
                                         "contact_line_vis": "friends", "contact_discord": "alice.dc", "contact_discord_vis": "hidden",
                                         "contact_instagram": "@alice.ig", "contact_instagram_vis": "friends"})
    check("contacts saved", "設定已儲存" in r.text)
    page = alice.get("/me/settings").text
    check("settings show contact values", 'value="alice_line"' in page and 'value="alice.ig"' in page)
    r = alice.post("/me/settings", data={**SETTINGS, "display_name": "Alice", "contact_line": "alice_line", "contact_line_vis": "friends",
                                         "contact_discord": "Bad Name!!", "contact_instagram": "alice.ig", "contact_instagram_vis": "friends"})
    check("invalid handle rejected, others kept", "Discord 的格式不正確" in r.text and 'value="alice.dc"' in alice.get("/me/settings").text)
    check("strangers never see contacts", "alice_line" not in bob.get("/u/alice").text and "alice_line" not in anon.get("/u/alice").text)
    befriend(alice, bob, "alice", "bob")
    page = bob.get("/u/alice").text
    check("friends see friends-only contacts", "alice_line" in page and 'href="https://www.instagram.com/alice.ig/"' in page)
    check("hidden contact stays hidden from friends", "alice.dc" not in page)
    check("owner sees all, with hidden marker", "alice.dc" in alice.get("/u/alice").text and "（不公開）" in alice.get("/u/alice").text)

    # ---------- 私訊 ----------
    check("message button for friends", 'href="/me/messages/alice"' in bob.get("/u/alice").text)
    check("no message button for strangers", 'href="/me/messages/alice"' not in carol.get("/u/alice").text)
    check("strangers can't open a chat", carol.get("/me/messages/alice").status_code == 404)
    check("strangers can't send", carol.post("/me/messages/alice", data={"body": "hi"}).status_code == 404)
    with Session(engine) as s:
        uid = {u.username: u.id for u in s.exec(select(User))}
        w = Work(category=Category.anime, source="anilist", external_id="1", title="迷宮飯")
        s.add(w)
        s.flush()
        s.add_all([CollectionEntry(user_id=uid["alice"], work_id=w.id), CollectionEntry(user_id=uid["bob"], work_id=w.id)])
        s.commit()
    page = bob.get("/me/messages/alice").text
    check("empty chat offers shared-interest openers", "你也喜歡《迷宮飯》嗎？" in page)
    r = bob.post("/me/messages/alice", data={"body": "嗨！"}, headers={"X-Requested-With": "fetch"})
    check("send via fetch", r.status_code == 200 and r.json()["body"] == "嗨！" and r.json()["mine"])
    check("empty message rejected", bob.post("/me/messages/alice", data={"body": "  "}, headers={"X-Requested-With": "fetch"}).status_code == 400)
    check("too long rejected", bob.post("/me/messages/alice", data={"body": "字" * 1001}, headers={"X-Requested-With": "fetch"}).status_code == 400)
    page = alice.get("/feed").text
    check("unread badge in nav", re.search(r'aria-label="0 個好友邀請、1 則未讀訊息">1<', page) is not None)
    inbox = alice.get("/me/messages").text
    check("inbox lists conversation as unread", "inbox-row unread" in inbox and "嗨！" in inbox)
    chat = alice.get("/me/messages/bob").text
    check("thread shows message", "嗨！" in chat)
    check("opening the chat marks it read", "inbox-row unread" not in alice.get("/me/messages").text)
    last = int(re.findall(r'data-id="(\d+)"', chat)[-1])
    alice.post("/me/messages/bob", data={"body": "你好"})
    new = bob.get(f"/me/messages/alice/new?after={last}").json()["messages"]
    check("polling returns only new messages", [m["body"] for m in new] == ["你好"] and not new[0]["mine"])
    check("inbox suggests friends without a chat", "和好友開始聊天" not in bob.get("/me/messages").text)
    bob.post("/friends/alice/block")
    check("blocking stops messages", bob.post("/me/messages/alice", data={"body": "x"}).status_code == 404
          and alice.get("/me/messages/bob").status_code == 404)
    check("blocked conversation leaves inbox", "Alice" not in bob.get("/me/messages").text)
    bob.post("/friends/alice/unblock")

    # ---------- 新手教學 ----------
    page = dave.get("/me/collection").text
    check("new user sees the checklist", "開始使用 YODO" in page and "新手教學 · 0 / 5" in page)
    with Session(engine) as s:
        d = s.get(User, uid["dave"])
        d.bio = "hi"
        s.add(d)
        s.commit()
    check("steps tick themselves off", "新手教學 · 1 / 5" in dave.get("/feed").text)
    r = dave.post("/me/onboarding/hide", headers={"referer": "http://testserver/feed"})
    check("hide returns to the page", "開始使用 YODO" not in r.text and str(r.url).endswith("/feed"))
    check("settings can reopen", "重新顯示新手教學" in dave.get("/me/settings").text)
    check("reopen", "開始使用 YODO" in dave.post("/me/onboarding/show").text)
    check("not shown on others' profiles", "開始使用 YODO" not in dave.get("/u/alice").text)

    # ---------- 附近 ----------
    check("coarse rounds to ~1 km", nearby.coarse(24.123456, 120.678912) == (24.12, 120.68))
    check("bad coordinates rejected", nearby.coarse(123, 0) is None)
    page = carol.get("/nearby").text
    check("nearby asks for a location first", "使用目前位置" in page and "說點什麼" not in page)
    check("explore tabs on both pages", 'href="/nearby"' in carol.get("/match").text and 'aria-current="page">附近的人' in page)
    carol.post("/nearby/location", data={"lat": "24.123456", "lon": "120.678912"})
    page = carol.get("/nearby").text
    check("location stored coarsely (session only)", "目前位置（約略到 1 公里）" in page and "24.123" not in page)
    r = carol.post("/nearby", data={"body": "附近有人喜歡迷宮飯嗎？", "radius": "3"})
    check("publish", "附近有人喜歡迷宮飯嗎？" in r.text and "還有 24 小時" in r.text)
    with Session(engine) as s:
        post = s.exec(select(NearbyPost)).one()
    check("post stores only grid coordinates", (post.lat, post.lon) == (24.12, 120.68))
    dave.post("/nearby/location", data={"lat": "24.135", "lon": "120.69"})  # ~2 km away
    page = dave.get("/nearby").text
    check("people within reach see it with a distance bucket", "附近有人喜歡迷宮飯嗎？" in page and "約 3 公里內" in page)
    check("no precise location shown", "120.68" not in page and "24.12" not in page)
    alice.post("/nearby/location", data={"region": "台北市"})
    check("far away people don't see it", "附近有人喜歡迷宮飯嗎？" not in alice.get("/nearby").text)
    check("poster sees no responders yet", "還沒有人回應" in carol.get("/nearby").text)
    r = dave.post(f"/nearby/{post.id}/reply", data={"body": "我！"})
    check("reply opens a chat with context", str(r.url).endswith("/me/messages/carol") and "（附近）附近有人喜歡迷宮飯嗎？" in r.text and "我！" in r.text)
    page = carol.get("/nearby").text
    check("poster now sees the responder", "回應你的人" in page and 'href="/me/messages/dave"' in page)
    check("they can keep chatting", carol.post("/me/messages/dave", data={"body": "嗨"}).status_code == 200)
    check("replying twice redirects to the chat", dave.post(f"/nearby/{post.id}/reply", data={"body": "again"}).status_code == 200)
    check("out of range can't reply", alice.post(f"/nearby/{post.id}/reply", data={"body": "x"}).status_code == 404)
    with Session(engine) as s:
        msgs = s.exec(select(Message).where(Message.body == "again")).all()
    check("second reply ignored", not msgs)
    carol.post("/nearby", data={"body": "第二則測試", "radius": "10"})
    check("second post visible before expiry", "第二則測試" in dave.get("/nearby").text)
    check("new post replaces the old one", "附近有人喜歡迷宮飯嗎？" not in dave.get("/nearby").text)
    with Session(engine) as s:
        live = s.exec(select(NearbyPost).where(NearbyPost.cancelled == False)).one()  # noqa: E712
        live.expires_at = utcnow() - timedelta(minutes=1)
        s.add(live)
        s.commit()
    check("expired posts disappear", "第二則測試" not in dave.get("/nearby").text)
    r = carol.post("/nearby", data={"body": "再一次", "radius": "10"})
    pid = int(re.search(r'/nearby/(\d+)/cancel', r.text).group(1))
    carol.post(f"/nearby/{pid}/cancel")
    check("cancel removes it", "再一次" not in dave.get("/nearby").text)
    carol.post("/nearby", data={"body": "封鎖測試", "radius": "10"})
    dave.post("/friends/carol/block")
    check("blocked users don't see each other's posts", "封鎖測試" not in dave.get("/nearby").text)
    check("forget location", "使用目前位置" in dave.post("/nearby/forget").text and "說點什麼" not in dave.get("/nearby").text)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
