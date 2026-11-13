import os
import pathlib
import re
from datetime import date

db = pathlib.Path(__file__).parent / "test_match.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CategoryPrivacy, CollectionEntry, Friendship, FriendStatus, User, Visibility, Work  # noqa: E402

PW = "testpass123"


def card(html, name):
    return next((a for a in re.findall(r'<article class="match-card"[^>]*>.*?</article>', html, re.S) if f'data-user="{name}"' in a), "")


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


with TestClient(app) as alice, TestClient(app) as bob_c, TestClient(app) as r1, TestClient(app) as r2, TestClient(app) as r3:
    with Session(engine) as s:
        def user(name, birth=date(2000, 1, 1), **kw):
            u = User(username=name, display_name=name.title(), password_hash=hash_password(PW), birth_date=birth, **kw)
            s.add(u)
            s.flush()
            return u

        def work(title, cat, creator=None):
            w = Work(category=cat, source="test", external_id=title, title=title, creator=creator)
            s.add(w)
            s.flush()
            return w

        def has(u, w, **kw):
            s.add(CollectionEntry(user_id=u.id, work_id=w.id, **kw))

        a1 = work("Rare Anime", Category.anime)
        a2 = work("Popular Anime", Category.anime)
        g1 = work("Deep Game", Category.game)
        m1 = work("Song One", Category.music, "Band")
        m2 = work("Song Two", Category.music, "band")  # same artist, different spelling
        extra = work("Filler", Category.anime)
        shared_ex = work("Exclusion Bait", Category.anime)  # shared with users who must never be recommended

        alice_u = user("alice", region="台北市", looking_for="game,anime")
        has(alice_u, a1, tier="must_watch")
        has(alice_u, a2)
        has(alice_u, g1, playtime_minutes=300 * 60)
        has(alice_u, m1, play_count=40)
        has(alice_u, shared_ex)

        bob = user("bob", region="台北市", looking_for="anime", bio="RPG 和冷門番")
        has(bob, a1, tier="must_watch")
        has(bob, g1, playtime_minutes=250 * 60)
        has(bob, m2, play_count=30)
        s.add(CategoryPrivacy(user_id=bob.id, category=Category.music, visibility=Visibility.private))

        carol = user("carol")
        has(carol, a2)
        dave = user("dave")
        has(dave, extra)
        for name, extra_kw in (("eve", {"hide_from_match": True}), ("frank", {}), ("gina", {})):
            u = user(name, **extra_kw)
            has(u, shared_ex)
            if name == "frank":
                s.add(Friendship(requester_id=alice_u.id, addressee_id=u.id, status=FriendStatus.accepted))
            if name == "gina":
                from app.models import Block
                s.add(Block(blocker_id=u.id, blocked_id=alice_u.id))
        minor = user("minor", birth=date.today().replace(year=date.today().year - 15))
        has(minor, shared_ex)
        legacy = user("legacy", birth=None)  # hasn't confirmed age
        has(legacy, shared_ex)
        for i in range(10):  # make Popular Anime popular; fillers don't want to be matched
            f = user(f"fan{i}", hide_from_match=True)
            has(f, a2)
        newbie = user("newbie")
        has(newbie, a2)
        s.commit()

    alice.post("/login", data={"username": "alice", "password": PW})
    r = alice.get("/match")
    names = re.findall(r'<article class="match-card" data-user="([a-z0-9_]+)"', r.text)
    check("bob (rare shared tastes) ranks first", names[:1] == ["bob"])
    check("carol (popular shared anime) ranks lower", "carol" in names and names.index("carol") > names.index("bob"))
    check("no shared interest -> not listed", "dave" not in names)
    for who, why in (("eve", "opted out"), ("frank", "already friends"), ("gina", "blocked"), ("minor", "under 18"), ("legacy", "age unconfirmed")):
        check(f"excluded: {why}", who not in names)
    bob_card = card(r.text, "bob")
    check("same-tier reason with 冷門 badge", '<span class="rare">冷門</span>你們都把《Rare Anime》評為「此生必看」' in bob_card)
    check("playtime reason uses the smaller side's hours", "你們都在《Deep Game》玩了超過 200 小時" in bob_card)
    check("private music not used", "Band" not in bob_card and "band" not in bob_card)
    check("same region + common looking-for shown", "台北市" in bob_card and "同地區" in bob_card and "都想聊動畫" in bob_card)
    check("bio shown", "RPG 和冷門番" in bob_card)
    check("visitor can add as friend from card", 'action="/friends/bob/request"' in bob_card)

    with Session(engine) as s:
        p = s.exec(select(CategoryPrivacy).where(CategoryPrivacy.user_id == s.exec(select(User).where(User.username == "bob")).one().id)).one()
        p.visibility = Visibility.public
        s.add(p)
        s.commit()
    bob_card = card(alice.get("/match").text, "bob")
    check("public music: shared artist across spellings", "你們都愛聽 Band" in bob_card and "3 項共同喜好" in bob_card)

    # dismiss
    alice.post("/match/carol/dismiss")
    check("不感興趣 removes carol", "/u/carol" not in alice.get("/match").text)

    # reports: three different people flag bob -> out of everyone's recommendations
    for c, name in ((r1, "rep1"), (r2, "rep2"), (r3, "rep3")):
        c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": PW, "birth_date": "1999-01-01"})
    r = r1.post("/report/bob", data={"reason": ""})
    check("report needs a reason", "請選擇檢舉原因" in r.text)
    r1.post("/report/bob", data={"reason": "harassment", "detail": "<b>x</b>"})
    r2.post("/report/bob", data={"reason": "other"})
    check("two reports: still recommended", 'href="/u/bob"' in alice.get("/match").text)
    r3.post("/report/bob", data={"reason": "inappropriate", "also_block": "true"})
    check("three reporters: removed pending review", 'href="/u/bob"' not in alice.get("/match").text)
    check("report + block blocks", r3.get("/u/bob").status_code == 404)

    # admin review
    check("non-admin can't open reports", alice.get("/admin/reports").status_code == 404)
    settings.admin_usernames = "alice"
    r = alice.get("/admin/reports")
    check("admin sees reports, detail escaped", r.status_code == 200 and r.text.count('class="report-row"') == 3 and "&lt;b&gt;x&lt;/b&gt;" in r.text)
    for rid in re.findall(r'action="/admin/reports/(\d+)/resolve"', r.text):
        alice.post(f"/admin/reports/{rid}/resolve")
    check("resolved reports: bob back in recommendations", 'href="/u/bob"' in alice.get("/match").text)
    settings.admin_usernames = ""

    # settings round trip + opt out
    r = bob_c.post("/login", data={"username": "bob", "password": PW})
    bob_c.post("/me/settings", data={"display_name": "Bob", "bio": "", "region": "火星", "looking_for": ["live", "bogus"],
                                     "visibility_game": "public", "visibility_anime": "public", "visibility_music": "public"})
    with Session(engine) as s:
        b = s.exec(select(User).where(User.username == "bob")).one()
        check("settings: invalid region dropped, looking_for filtered, unchecked = opted out",
              b.region is None and b.looking_for == "live" and b.hide_from_match is True)
    check("opted-out user leaves recommendations", 'href="/u/bob"' not in alice.get("/match").text)
    page = bob_c.get("/u/bob").text
    check("profile shows looking-for chip", "想找：一起去演唱會、展覽" in page)

    # viewer with too little data
    newbie = TestClient(app)
    with newbie:
        newbie.post("/login", data={"username": "newbie", "password": PW})
        r = newbie.get("/match")
        check("too few entries -> explains why", "至少要有 3 個公開的收藏" in r.text)
        check("tabs: 探索 tab highlighted on /match", 'href="/match" aria-current="page"' in r.text)
