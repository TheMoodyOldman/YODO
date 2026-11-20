"""Demo-day polish: 新加入的同好 doesn't repeat people already recommended (E), Recap hours without a
stray ".0" (F), the Recap footer shows the product site (G), no space after the full-width comma
on the 契合度 result (J), and the 我的 sub-menu wraps on phones instead of being cut off (M)."""

import os
import pathlib
import re
from datetime import date

here = pathlib.Path(__file__).parent
db = here / "test_polish.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import card_render  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, FriendStatus, Friendship, MonthlyPlays, User, Work  # noqa: E402
from app.routers import card as card_router  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


init_db()
viewer = TestClient(app)
viewer.post("/register", data={"username": "viewer", "email": "viewer@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})

with Session(engine) as s:
    works = []
    for i in range(4):
        w = Work(category=Category.anime, source="anilist", external_id=str(i), title=f"Show {i}")
        s.add(w)
        s.flush()
        works.append(w)
    me = s.exec(select(User).where(User.username == "viewer")).one()
    for w in works[:3]:
        s.add(CollectionEntry(user_id=me.id, work_id=w.id, tier="great"))
    for name, shared in (("ana", works[:2]), ("ben", works[1:3]), ("newbie", [])):
        u = User(username=name, display_name=name.title(), password_hash="x", birth_date=date(2000, 1, 1))
        s.add(u)
        s.flush()
        for w in shared:
            s.add(CollectionEntry(user_id=u.id, work_id=w.id, tier="great"))
    s.commit()

page = viewer.get("/match").text
cards = re.findall(r'<article class="match-card" data-user="([a-z0-9_]+)"', page)
newcomers = page.split('class="newcomers"')[1] if 'class="newcomers"' in page else ""
listed = re.findall(r'class="feed-name" href="/u/([a-z0-9_]+)"', newcomers)
check("E: two recommendations", sorted(cards) == ["ana", "ben"], str(cards))
check("E: 新加入的同好 lists only people not already recommended", listed == ["newbie"], str(listed))

check("F: whole hours have no .0", card_render._hours(540) == "9 小時" and card_render._hours(1320) == "22 小時")
check("F: one decimal kept when it means something", card_render._hours(90) == "1.5 小時" and card_render._hours(594) == "9.9 小時")

# G: the footer handed to the renderer
with Session(engine) as s:
    me = s.exec(select(User).where(User.username == "viewer")).one()
    song = Work(category=Category.music, source="lastfm", external_id="a␟b", title="Song", creator="Artist")
    s.add(song)
    s.flush()
    s.add(CollectionEntry(user_id=me.id, work_id=song.id, play_count=5))
    s.add(MonthlyPlays(user_id=me.id, work_id=song.id, month="2026-11", plays=5))
    s.commit()
seen = {}
real_render = card_router.render_card


def spy(stats, name, footer, categories, images):
    seen["footer"] = footer
    return real_render(stats, name, footer, categories, images)


card_router.render_card = spy
try:
    r = viewer.get("/me/card/image.jpg?period=month&key=2026-11&c=music")
finally:
    card_router.render_card = real_render
check("G: Recap footer is the product site", r.status_code == 200 and seen.get("footer") == "https://qwqohmy.github.io/yodo-site/",
      str(seen))

# J: 契合度 result text
with Session(engine) as s:
    me = s.exec(select(User).where(User.username == "viewer")).one()
    ana = s.exec(select(User).where(User.username == "ana")).one()
    s.add(Friendship(requester_id=me.id, addressee_id=ana.id, status=FriendStatus.accepted))
    s.commit()
text = re.sub(r"<[^>]+>", "", viewer.get("/games/compat/ana?guess=0").text)
check("J: no space after the full-width comma", "你猜 0%，差了" in text and "%， " not in text, re.findall(r"你猜.{0,20}", text)[:1])

css = (pathlib.Path(__file__).resolve().parent.parent / "app/static/css/style.css").read_text(encoding="utf-8")
check("M: 我的 sub-menu wraps on phones", re.search(r"@media \(max-width: 640px\) \{\s*\.my-nav \{ flex-wrap: wrap;", css) is not None)

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
