import os
import pathlib
import re

here = pathlib.Path(__file__).parent
db = here / "test_community.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["ADMIN_USERNAMES"] = "admin1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import workinfo  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, Post, Report, Review, User, Visibility, Work  # noqa: E402
from app.privacy import set_privacy  # noqa: E402


async def no_info(work):
    return workinfo.WorkInfo()


workinfo.get_work_info = no_info
import app.routers.community as community_router  # noqa: E402
import app.routers.work as work_router  # noqa: E402

community_router.get_work_info = no_info
work_router.get_work_info = no_info

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


with TestClient(app):
    alice, bob, carol, dave, admin, = (client(n) for n in ("alice", "bob", "carol", "dave", "admin1"))
    anon = TestClient(app)
    with Session(engine) as s:
        uid = {u.username: u.id for u in s.exec(select(User))}
        anime = Work(category=Category.anime, source="anilist", external_id="1", title="迷宮飯", original_title="ダンジョン飯")
        game = Work(category=Category.game, source="steam", external_id="2", title="Hades")
        book = Work(category=Category.book, source="openlibrary", external_id="OL3W", title="三體")
        s.add_all([anime, game, book])
        s.flush()
        s.add_all([
            CollectionEntry(user_id=uid["alice"], work_id=anime.id, tier="must_watch", tag="神作"),
            CollectionEntry(user_id=uid["bob"], work_id=anime.id, tier="great", tag="神作"),
            CollectionEntry(user_id=uid["carol"], work_id=anime.id, tier="great", tag="好甜"),
            CollectionEntry(user_id=uid["dave"], work_id=anime.id, tier="bad", hidden=True),  # hidden: not counted
            CollectionEntry(user_id=uid["alice"], work_id=game.id, playtime_minutes=600),
            CollectionEntry(user_id=uid["bob"], work_id=game.id, playtime_minutes=1200),
            CollectionEntry(user_id=uid["alice"], work_id=book.id, status="read", tier="good"),
            CollectionEntry(user_id=uid["bob"], work_id=book.id, status="want"),
        ])
        set_privacy(s, uid["carol"], Category.anime, Visibility.private)
        s.commit()
        aid, gid, bid = anime.id, game.id, book.id

    # ---------- stats ----------
    page = anon.get(f"/w/{aid}").text
    check("public page visible logged out", "大家的評價" in page and "迷宮飯" in page)
    check("collectors exclude hidden, include private", "3 人" in page)
    check("tier distribution", re.search(r"大推</span>.*?67%", page, re.S) is not None and re.search(r"此生必看</span>.*?33%", page, re.S) is not None)
    check("top tags with counts", "#神作 <span class=\"muted\">2</span>" in page)
    check("anonymous note", "以匿名方式計入" in page)
    check("logged-out prompt", "登入後加入收藏、寫短評" in page and "review-form" not in page)
    page = anon.get(f"/w/{gid}").text
    check("game shows average hours", "平均遊玩" in page and "15" in page)
    page = anon.get(f"/w/{bid}").text
    check("book status counts", "讀完 1" in page and "想讀 1" in page)
    check("unknown work 404", anon.get("/w/999").status_code == 404)

    # ---------- reviews ----------
    r = alice.post(f"/w/{aid}/review", data={"body": "  料理和冒險都好看  "})
    check("post review", "已發布短評" in r.text and "料理和冒險都好看" in r.text)
    alice.post(f"/w/{aid}/review", data={"body": "第二版：超推"})
    with Session(engine) as s:
        rows = s.exec(select(Review).where(Review.work_id == aid)).all()
    check("one review per user, updated", len(rows) == 1 and rows[0].body == "第二版：超推")
    check("empty review rejected", "短評請寫" in alice.post(f"/w/{aid}/review", data={"body": "  "}).text)
    check("too long review rejected", "短評請寫" in alice.post(f"/w/{aid}/review", data={"body": "字" * 501}).text)
    carol.post(f"/w/{aid}/review", data={"body": "結局是……", "spoiler": "true"})
    page = bob.get(f"/w/{aid}").text
    check("spoiler folded", '<details class="spoiler">' in page and "有雷，點一下顯示" in page)
    check("reviewer verdict shown when category public", "tier-must_watch" in page.split("第二版")[0].rsplit("<li", 1)[-1])
    carol_li = page.split("結局是")[0].rsplit("<li", 1)[-1]
    check("private category hides reviewer verdict", "tier-" not in carol_li)

    rid = rows[0].id
    r = bob.post(f"/reviews/{rid}/like", headers={"X-Requested-With": "fetch"})
    check("like via fetch", r.json() == {"likes": 1, "liked": True})
    r = bob.post(f"/reviews/{rid}/like", headers={"X-Requested-With": "fetch"})
    check("unlike", r.json() == {"likes": 0, "liked": False})
    bob.post(f"/reviews/{rid}/like")
    r = alice.post(f"/reviews/{rid}/like", headers={"X-Requested-With": "fetch"})
    check("can't like own review", r.json()["likes"] == 1 and r.json()["liked"] is False)
    with Session(engine) as s:
        carol_rid = s.exec(select(Review).where(Review.user_id == uid["carol"])).one().id
    page = dave.get(f"/w/{aid}").text
    check("most-liked first", page.index("第二版") < page.index("結局是"))
    page = dave.get(f"/w/{aid}?sort=new").text
    check("newest sort", page.index("結局是") < page.index("第二版"))
    page = carol.get(f"/w/{aid}").text
    check("own review first and prefilled", page.index("結局是") < page.index("第二版") and ">結局是……</textarea>" in page)
    check("delete others' review forbidden", bob.post(f"/reviews/{carol_rid}/delete").status_code == 404)

    # ---------- comments ----------
    bob.post(f"/w/{aid}/comments", data={"body": "有人看了漫畫嗎"})
    page = anon.get(f"/w/{aid}").text
    check("comment shown", "有人看了漫畫嗎" in page and "留言區" in page)
    with Session(engine) as s:
        from app.models import WorkComment
        cid = s.exec(select(WorkComment)).one().id
    check("others can't delete comment", alice.post(f"/work-comments/{cid}/delete").status_code == 404)
    check("admin can delete comment", admin.post(f"/work-comments/{cid}/delete").status_code == 200
          and "有人看了漫畫嗎" not in anon.get(f"/w/{aid}").text)

    # ---------- blocks ----------
    bob.post("/friends/alice/block")
    page = bob.get(f"/w/{aid}").text
    check("blocked author's review hidden", "第二版" not in page and "結局是" in page)
    bob.post(f"/w/{aid}/comments", data={"body": "bob 的留言"})
    check("blocker's posts hidden from the blocked user too", "bob 的留言" not in alice.get(f"/w/{aid}").text
          and "bob 的留言" in carol.get(f"/w/{aid}").text)
    bob.post("/friends/alice/unblock")

    # ---------- add from public page, link from personal page ----------
    page = dave.get(f"/w/{bid}").text
    check("add button for rated categories", f'action="/w/{bid}/add"' in page)
    r = dave.post(f"/w/{bid}/add")
    check("add redirects to rating dialog", "rate-dialog-book" in r.text and "data-autoopen" in r.text)
    check("then shows 在我的收藏中", "在我的收藏中" in dave.get(f"/w/{bid}").text)
    check("no add button for games", f'action="/w/{gid}/add"' not in dave.get(f"/w/{gid}").text)
    page = alice.get(f"/u/alice/w/{aid}").text
    check("personal page links to community", f'href="/w/{aid}"' in page and "2 則短評" in page)

    # ---------- report ----------
    page = bob.get(f"/w/{aid}").text
    check("report link carries context", f"/report/carol?about=%E7%9F%AD%E8%A9%95%20%23{carol_rid}" in page)
    bob.post("/report/carol", data={"reason": "inappropriate", "about": f"短評 #{carol_rid} /w/{aid}", "next": f"/w/{aid}"})
    with Session(engine) as s:
        rep = s.exec(select(Report)).one()
    check("report stores what was reported", rep.detail.startswith(f"[短評 #{carol_rid} /w/{aid}]"), rep.detail)
    check("admin can delete review", admin.post(f"/reviews/{carol_rid}/delete").status_code == 200)

    # ---------- 討論區 ----------
    page = anon.get("/discuss").text
    check("board visible logged out", "討論區" in page and "登入</a>後就能貼便利貼" in page)
    r = alice.post("/discuss", data={"category": "anime", "body": "這季大家追什麼？", "color": "pink"})
    check("post note -> thread", "這季大家追什麼？" in r.text and "note-pink" in r.text and str(r.url).endswith(tuple("0123456789")))
    pid = int(str(r.url).rsplit("/", 1)[-1])
    check("note needs category", "請選擇分類" in alice.post("/discuss", data={"body": "x"}).text)
    check("note length limit", "便利貼請寫" in alice.post("/discuss", data={"category": "game", "body": "字" * 201}).text)
    alice.post("/discuss", data={"category": "game", "body": "推薦 roguelike", "color": "nope", "spoiler": "true"})
    page = anon.get("/discuss").text
    check("wall newest first", page.index("note-cat\">遊戲") < page.index("這季大家追什麼？"))
    check("spoiler note folded on wall", "有雷，點開看" in page and "推薦 roguelike" not in page)
    check("bad color falls back", page.count("note-yellow") >= 1)
    page = anon.get("/discuss?c=anime").text
    check("category filter", "這季大家追什麼？" in page and "有雷，點開看" not in page)
    bob.post(f"/discuss/{pid}/replies", data={"body": "迷宮飯第二季！"})
    alice.post(f"/discuss/{pid}/replies", data={"body": "我也是"})
    page = anon.get(f"/discuss/{pid}").text
    check("replies + 樓主 badge", "迷宮飯第二季！" in page and "樓主" in page)
    with Session(engine) as s:
        post = s.get(Post, pid)
    check("reply count kept", post.reply_count == 2)
    page = anon.get("/discuss").text
    check("thread with new reply bumped to top", page.index("這季大家追什麼？") < page.index("note-cat\">遊戲"))
    with Session(engine) as s:
        from app.models import PostReply
        bob_reply = s.exec(select(PostReply).where(PostReply.user_id == uid["bob"])).one().id
    check("thread owner can delete a reply", alice.post(f"/discuss/replies/{bob_reply}/delete").status_code == 200
          and "迷宮飯第二季！" not in anon.get(f"/discuss/{pid}").text)
    check("others can't delete note", carol.post(f"/discuss/{pid}/delete").status_code == 404)
    bob.post("/friends/alice/block")
    check("blocked user's notes hidden", "這季大家追什麼" not in bob.get("/discuss").text and bob.get(f"/discuss/{pid}").status_code == 404)
    check("blocked can't reply", bob.post(f"/discuss/{pid}/replies", data={"body": "hi"}).status_code == 404)
    r = alice.post(f"/discuss/{pid}/delete")
    check("owner deletes note", "已刪除便利貼" in r.text and anon.get(f"/discuss/{pid}").status_code == 404)

    # ---------- 7-day wall ----------
    from datetime import timedelta
    from app.models import utcnow
    r = carol.post("/discuss", data={"category": "music", "body": "上週的舊話題", "color": "blue"})
    old_id = int(str(r.url).rsplit("/", 1)[-1])
    with Session(engine) as s:
        old = s.get(Post, old_id)
        old.created_at = utcnow() - timedelta(days=8)
        s.add(old)
        s.commit()
    wall = anon.get("/discuss").text
    check("wall explains the 7-day limit", "便利貼只會在牆上留 7 天" in wall)
    check("notes older than 7 days leave the wall", "上週的舊話題" not in wall and "上週的舊話題" not in anon.get("/discuss?c=music").text)
    page = anon.get(f"/discuss/{old_id}").text
    check("old note still opens by link, with a hint", "上週的舊話題" in page and "已經超過 7 天" in page)
    check("old note still accepts replies", "還是可以" in alice.post(f"/discuss/{old_id}/replies", data={"body": "還是可以回"}).text)
    check("fresh notes have no expiry hint", "已經超過" not in anon.get("/discuss").text)

    # ---------- nav ----------
    check("nav has 討論", 'href="/discuss"' in alice.get("/feed").text)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
