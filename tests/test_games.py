import io
import os
import pathlib
import re
from datetime import date

db = pathlib.Path(__file__).parent / "test_games.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

import app.routers.games as games_router  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.games import FREE, PROMPT_BY_KEY, bingo_board, bingo_lines, bingo_marked, current_month  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Block, Category, CategoryPrivacy, CollectionEntry, Friendship, FriendStatus, User, Visibility, Work,
)

PW = "testpass123"


async def no_images(urls):
    return {}


games_router.fetch_images = no_images


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def jpeg_ok(resp):
    try:
        return resp.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(resp.content)).size == (1080, 1920)
    except Exception:
        return False


with Session(engine) as s:
    pass

with TestClient(app) as alice, TestClient(app) as lonely:
    with Session(engine) as s:
        def user(name, birth=date(2000, 1, 1)):
            u = User(username=name, display_name=name.title(), password_hash=hash_password(PW), birth_date=birth)
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

        def friends(a, b):
            s.add(Friendship(requester_id=a.id, addressee_id=b.id, status=FriendStatus.accepted))

        A = user("alice"); B = user("bob"); C = user("carol"); D = user("dave"); E = user("eve"); M = user("minor", date(2015, 1, 1))
        L = user("lonely")
        shared_game = work("Shared Game", Category.game)
        shared_anime = work("Shared Anime", Category.anime)
        secret = work("Secret Song", Category.music, "Hidden Band")
        bob_only = [work(f"Bob Pick {i}", Category.game) for i in range(3)]
        carol_only = [work(f"Carol Pick {i}", Category.anime) for i in range(3)]
        alice_only = work("Alice Only", Category.anime)
        dave_private = work("Dave Private", Category.anime)

        has(A, shared_game, playtime_minutes=150 * 60)
        has(A, shared_anime, tier="must_watch")
        has(A, alice_only, tier="great")
        has(A, secret, play_count=10)
        has(A, dave_private, tier="good")
        has(B, shared_game, playtime_minutes=120 * 60)
        has(B, shared_anime, tier="must_watch")
        for i, w in enumerate(bob_only):
            has(B, w, playtime_minutes=(30 + i) * 60)
        has(B, secret, play_count=99)
        s.add(CategoryPrivacy(user_id=B.id, category=Category.music, visibility=Visibility.private))
        for w in carol_only:
            has(C, w, tier="great")
        has(D, shared_anime)
        has(D, dave_private, tier="good")
        s.add(CategoryPrivacy(user_id=D.id, category=Category.anime, visibility=Visibility.private))
        has(D, shared_game, playtime_minutes=60)
        friends(A, B); friends(C, A)
        s.add(Block(blocker_id=E.id, blocked_id=A.id))
        s.commit()
        ids = {"bob": B.id, "carol": C.id}
        titles = {B.id: {w.title for w in bob_only} | {"Shared Game", "Shared Anime"}, C.id: {w.title for w in carol_only}}

    alice.post("/login", data={"username": "alice", "password": PW})

    # ---------- hub + nav
    r = alice.get("/games")
    check("games hub lists the games, without Recap", all(t in r.text for t in ("品味契合度挑戰", "猜猜這是誰的收藏", "興趣賓果", "猜誰是臥底", "猜歌對戰", "30 天挑戰")) and "Recap 分享卡" not in r.text)
    check("nav has 小遊戲", 'href="/games"' in r.text and 'href="/games" aria-current="page"' in r.text and "<span>小遊戲</span>" in r.text)
    check("profile offers 測契合度", 'href="/games/compat/bob"' in alice.get("/u/bob").text)

    # ---------- compat
    r = alice.get("/games/compat/bob")
    check("compat asks for a guess first", 'name="guess"' in r.text and "compat-pct" not in r.text)
    r = alice.get("/games/compat/bob", params={"guess": "60"})
    pct = int(re.search(r'class="compat-pct">(\d+)<', r.text).group(1))
    check(f"compat result shown ({pct}%) with guess feedback", 0 <= pct <= 100 and "你猜 60%" in r.text)
    check("shared favourites listed", "Shared Anime" in r.text.split("你們都愛")[1])
    check("bob's private music never used", "Secret Song" not in r.text and "音樂" not in r.text.split("compat-label")[1].split("你們都愛")[0])
    picks = r.text.split("Bob 推薦你")[1].split("</section>")[0] if "Bob 推薦你" in r.text else ""
    check("their picks exclude what alice has", "Bob Pick" in picks and "Shared Game" not in picks)
    r = alice.get("/games/compat/dave", params={"guess": "skip"})
    check("non-friend: private anime not compared", "Dave Private" not in r.text and "動畫" not in r.text.split("compat-label")[1].split("</section>")[0])
    check("compat card is a 1080x1920 JPEG", jpeg_ok(alice.get("/games/compat/bob/card.jpg")))
    check("self / blocked / under-18 -> 404", all(alice.get(f"/games/compat/{u}").status_code == 404 for u in ("alice", "eve", "minor")))
    with Session(engine) as s:  # identical collections = 100%
        from app.games import compatibility
        a = s.exec(select(User).where(User.username == "alice")).one()
        res = compatibility(s, a, a, True)
        check("identical collections -> 100% 靈魂伴侶", res.pct == 100 and res.label == "靈魂伴侶")

    # ---------- guess
    r = lonely.post("/login", data={"username": "lonely", "password": PW})
    check("guess needs 2 friends", "需要至少 2 位好友" in lonely.get("/games/guess").text)
    check("card before finishing -> 404", alice.get("/games/guess/card.jpg").status_code == 404)
    seen_titles, rounds = set(), 0
    for _ in range(5):
        r = alice.get("/games/guess")
        shown = set(re.findall(r'<div class="card-title">([^<]+)</div>', r.text.split("guess-items")[1].split("這是誰的收藏？")[0]))
        seen_titles |= shown
        answer = next(uid for uid, t in titles.items() if shown <= t)
        options = [int(x) for x in re.findall(r'name="choice" value="(\d+)"', r.text)]
        check_round = answer in options and 2 <= len(options) <= 4
        rounds += check_round
        alice.post("/games/guess/answer", data={"choice": answer})
    check("5 rounds, each with the right friend among 2-4 options", rounds == 5)
    check("only visible items shown (no private music)", "Secret Song" not in seen_titles)
    r = alice.get("/games/guess")
    check("perfect score result", 'class="compat-pct">5<' in r.text and "好友雷達滿分" in r.text)
    alice.post("/games/guess/answer", data={"choice": ids["bob"]})
    check("answers after the end are ignored", 'class="compat-pct">5<' in alice.get("/games/guess").text)
    check("guess card is a 1080x1920 JPEG", jpeg_ok(alice.get("/games/guess/card.jpg")))
    alice.post("/games/guess/new")
    r = alice.get("/games/guess")
    check("new game restarts at round 1", "第 1 / 5 題 · <strong class=\"round-score\">0 分</strong>" in r.text)
    alice.post("/games/guess/answer", data={"choice": 999999})
    check("choice not among options ignored", "第 1 / 5 題" in alice.get("/games/guess").text)

    # ---------- bingo
    month = current_month()
    with Session(engine) as s:
        a = s.exec(select(User).where(User.username == "alice")).one()
        board = bingo_board(a, month)
        check("board: 25 cells, FREE centre, stable", len(board) == 25 and board[12] == FREE and board == bingo_board(a, month))
        check("board: 10 auto squares", sum(1 for k in board if k != FREE and PROMPT_BY_KEY[k].auto) == 10)
        check("next month differs", board != bingo_board(a, "2099-01"))
        marked = bingo_marked(s, a, month, board)
        auto_game = PROMPT_BY_KEY["game_100h"].auto
        check("auto squares follow data", all(marked[i] == (PROMPT_BY_KEY[k].auto(__import__("app.games").games.bingo_stats(s, a)))
                                              for i, k in enumerate(board) if k != FREE and PROMPT_BY_KEY[k].auto))
    check("line counting", bingo_lines([True] * 25) == 12 and bingo_lines([i < 5 or i == 12 for i in range(25)]) == 1
          and bingo_lines([False] * 25) == 0)
    manual = next(k for k in board if k != FREE and not PROMPT_BY_KEY[k].auto)
    auto = next(k for k in board if k != FREE and PROMPT_BY_KEY[k].auto)
    r = alice.post("/games/bingo/toggle", data={"key": manual}, headers={"X-Requested-With": "fetch"})
    check("toggle manual square on (JSON)", r.status_code == 200 and r.json()["marked"] is True)
    r = alice.post("/games/bingo/toggle", data={"key": manual}, headers={"X-Requested-With": "fetch"})
    check("toggle off again", r.json()["marked"] is False)
    check("auto square can't be toggled", alice.post("/games/bingo/toggle", data={"key": auto}).status_code == 400)
    off_board = next(k for k in PROMPT_BY_KEY if k not in board and not PROMPT_BY_KEY[k].auto)
    check("square not on this board refused", alice.post("/games/bingo/toggle", data={"key": off_board}).status_code == 400)
    r = alice.get("/games/bingo")
    check("bingo page renders 25 cells", r.text.count('class="bingo-cell') == 25 and "條線" in r.text)
    check("bingo card is a 1080x1920 JPEG", jpeg_ok(alice.get("/games/bingo/card.jpg")))

    # ---------- share logging
    ok = alice.post("/me/card/events", json={"period": "bingo", "key": month, "action": "share"}).status_code
    bad = alice.post("/me/card/events", json={"period": "hack", "key": "x", "action": "share"}).status_code
    check("game shares logged, unknown kinds refused", ok == 204 and bad == 422)
    check("games require login", TestClient(app).get("/games/bingo", follow_redirects=False).status_code == 303)
