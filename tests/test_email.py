import os
import pathlib
import re
from urllib.parse import urlsplit

here = pathlib.Path(__file__).parent
db = here / "test_email.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["SMTP_HOST"] = "smtp.test.invalid"  # mail "configured" -> verification enforced
os.environ["MAIL_FROM"] = "YODO <no-reply@test.yodo>"

from fastapi.testclient import TestClient  # noqa: E402

from app import mail as mail_module  # noqa: E402
from app.main import app  # noqa: E402

sent = []
mail_module.send = lambda to, subject, body: sent.append((to, subject, body))

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def link_in(body):
    url = re.search(r"https?://\S+", body).group(0)
    parts = urlsplit(url)
    return parts.path + "?" + parts.query


def register(c, name, email):
    return c.post("/register", data={"username": name, "email": email, "password": "testpass123", "birth_date": "2000-01-01"})


with TestClient(app):
    alice, bob, anon = TestClient(app), TestClient(app), TestClient(app)

    r = register(alice, "alice", "not-an-email")
    check("invalid email rejected", r.status_code == 400 and "請填寫正確的電子信箱" in r.text)
    r = register(alice, "alice", "  Alice@Example.com ")
    check("register sends a verification email", "驗證信已寄到 alice@example.com" in r.text and sent and sent[-1][0] == "alice@example.com")
    check("email stored lowercase", "alice@example.com" in alice.get("/me/settings").text)
    r = register(bob, "bob", "ALICE@example.com")
    check("duplicate email rejected (case-insensitive)", r.status_code == 400 and "已經註冊過了" in r.text)
    register(bob, "bob", "bob@example.com")

    page = alice.get("/feed").text
    check("banner asks to verify", 'class="email-banner required"' in page)
    r = alice.post("/friends/bob/request")
    check("unverified: friend request -> verify page", str(r.url).endswith("/me/verify") and "請先驗證電子信箱" in r.text)
    r = alice.post("/discuss", data={"category": "anime", "body": "hi"})
    check("unverified: can't post notes", str(r.url).endswith("/me/verify"))
    check("unverified: can't open game rooms", str(alice.post("/games/song/new").url).endswith("/me/verify"))
    r = alice.post("/nearby", data={"body": "hi"}, headers={"X-Requested-With": "fetch"})
    check("fetch requests get JSON 403", r.status_code == 403 and "電子信箱" in r.json()["error"])
    check("unverified can still browse and manage collection", alice.get("/me/collection").status_code == 200)

    n_before = len(sent)
    check("resend right after sign-up is rate limited", "剛剛才寄過" in alice.post("/me/verify/resend").text and len(sent) == n_before)

    first_link = link_in([b for to, s, b in sent if to == "alice@example.com"][-1])
    r = anon.get(first_link)
    check("link works even when not logged in", "電子信箱驗證完成" in anon.get("/login").text or str(r.url).endswith("/login"))
    page = alice.get("/me/verify").text
    check("now verified", "✓ 已驗證" in page)
    check("banner gone", "email-banner" not in alice.get("/feed").text)
    r = alice.post("/friends/bob/request")
    check("verified: friend request works", not str(r.url).endswith("/me/verify"))
    check("bad token rejected", "驗證連結無效" in alice.get("/verify-email?token=garbage").text)

    # change email -> needs verifying again; old link no longer valid
    alice.post("/me/email", data={"email": "alice2@example.com"})
    check("changing email resets verification", "尚未驗證" in alice.get("/me/verify").text and sent[-1][0] == "alice2@example.com")
    check("old link (old address) is rejected", "驗證連結無效" in alice.get(first_link).text)
    check("can't take someone else's email", "已經有人使用" in alice.post("/me/email", data={"email": "bob@example.com"}).text)
    alice.get(link_in(sent[-1][2]))
    check("new address verified", "✓ 已驗證" in alice.get("/me/verify").text)

    # login with email
    alice.post("/logout")
    r = alice.post("/login", data={"username": "Alice2@example.com", "password": "testpass123"})
    check("login with email", r.status_code == 200 and "/login" not in str(r.url))

    # forgot password
    n = len(sent)
    r = anon.post("/forgot-password", data={"email": "nobody@example.com"})
    check("unknown email: same answer, no mail", "如果這個信箱有註冊" in r.text and len(sent) == n)
    r = TestClient(app).post("/forgot-password", data={"email": "bob@example.com"})
    check("unverified email gets no reset mail", len(sent) == n)
    TestClient(app).post("/forgot-password", data={"email": "alice2@example.com"})
    check("verified email gets a reset link", len(sent) == n + 1 and sent[-1][0] == "alice2@example.com" and "重設" in sent[-1][1])
    reset = link_in(sent[-1][2])
    page = anon.get(reset).text
    check("reset form shown", 'name="password"' in page)
    token = reset.split("token=", 1)[1]
    r = anon.post("/reset-password", data={"token": token, "password": "short"})
    check("short password rejected", "密碼至少" in r.text)
    r = anon.post("/reset-password", data={"token": token, "password": "newpass123"})
    check("password reset", "密碼已更新" in r.text)
    check("reset link is single-use", "無效、已過期，或已經用過了" in anon.get(reset).text)
    r = TestClient(app).post("/login", data={"username": "alice", "password": "testpass123"})
    check("old password no longer works", "帳號或密碼錯誤" in r.text)
    r = TestClient(app).post("/login", data={"username": "alice", "password": "newpass123"})
    check("new password works", "/login" not in str(r.url))
    check("login page links to forgot password", 'href="/forgot-password"' in anon.get("/login").text)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
