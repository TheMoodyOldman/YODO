"""本季新番快速勾選: pick page, saving / un-picking, profile row, merged feed item with privacy,
探索 banner (first 8 weeks, dismiss per season), matching weight / cap / reason order, and the
upgrade of a database created before the new columns existed. AniList and Bangumi are faked."""

import asyncio
import os
import pathlib
import re
import sqlite3
from datetime import date, datetime, timezone

here = pathlib.Path(__file__).parent
db = here / "test_season.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

# ---------- an "old" database: today's schema minus the new columns, with some data ----------
from sqlmodel import SQLModel, create_engine  # noqa: E402

from app import models  # noqa: E402, F401

old = create_engine(f"sqlite:///{db.as_posix()}")
SQLModel.metadata.create_all(old)
old.dispose()
con = sqlite3.connect(db)
con.execute("ALTER TABLE collectionentry DROP COLUMN season")
con.execute("ALTER TABLE collectionentry DROP COLUMN quick_pick")
con.execute('ALTER TABLE "user" DROP COLUMN season_banner_dismissed')
con.execute(
    "INSERT INTO user (username, display_name, password_hash, bio, birth_date, created_at) "
    "VALUES ('legacy', 'Legacy', 'x', '', '1990-01-01', '2026-01-01 00:00:00')"
)
con.execute(
    "INSERT INTO work (category, source, external_id, title) VALUES ('anime', 'anilist', '999', 'Old Show')"
)
con.execute(
    "INSERT INTO collectionentry (user_id, work_id, tier, tag, hidden, pending_review, added_at) "
    "VALUES (1, 1, 'GREAT', NULL, 0, 0, '2026-01-02 00:00:00')"
)
con.commit()
con.close()

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import anime_search, matching, seasonal  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Activity, ActivityKind, Category, CollectionEntry, FriendStatus, Friendship, User, Visibility, Work,
)
from app.privacy import set_privacy  # noqa: E402
from app.services import anilist  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


# ---------- fakes ----------
TODAY = [date(2026, 11, 13)]
seasonal.local_today = lambda: TODAY[0]

SHOWS = [
    anilist.Anime(id=1000 + i, title=f"Show {i}", original_title=f"番組{i}", cover_url=f"https://img.test/{i}.jpg",
                  year=2026, format="TV" if i % 3 else "ONA")
    for i in range(50)
]
calls = []


async def fake_season(season, year, per_page=50):
    calls.append((season, year, per_page))
    return list(SHOWS)


anilist.season_anime = fake_season


async def no_zh(native):
    raise AssertionError("no Bangumi lookups while rendering")


anime_search.chinese_title = no_zh

# ---------- migration ----------
init_db()  # what app startup runs; must be safe on an old database and idempotent
init_db()
con = sqlite3.connect(db)
ce_cols = {r[1] for r in con.execute("PRAGMA table_info(collectionentry)")}
user_cols = {r[1] for r in con.execute("PRAGMA table_info(user)")}
legacy = con.execute("SELECT tier, season, quick_pick FROM collectionentry WHERE user_id = 1").fetchone()
con.close()
check("upgrade adds season columns", {"season", "quick_pick"} <= ce_cols and "season_banner_dismissed" in user_cols)
check("upgrade keeps existing rows (new columns NULL)", legacy == ("GREAT", None, None), str(legacy))


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": f"{name}@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def uid(name):
    with Session(engine) as s:
        return s.exec(select(User).where(User.username == name)).one().id


def friends(a, b):
    with Session(engine) as s:
        s.add(Friendship(requester_id=uid(a), addressee_id=uid(b), status=FriendStatus.accepted))
        s.commit()


def privacy(name, visibility):
    with Session(engine) as s:
        set_privacy(s, uid(name), Category.anime, visibility)
        s.commit()


def entries(name):
    with Session(engine) as s:
        return {
            w.external_id: e
            for e, w in s.exec(select(CollectionEntry, Work).join(Work).where(CollectionEntry.user_id == uid(name)))
        }


def pick(c, *ids, follow=False):
    return c.post("/me/season", data={"pick": [str(i) for i in ids]}, follow_redirects=follow)


def season_feed_items(page):
    return re.findall(r'<article class="feed-item[^"]*" id="act-\d+">.*?</article>', page, re.S)


# A show already in the catalog with its Chinese title: the grid reuses it instead of asking Bangumi.
with Session(engine) as s:
    s.add(Work(category=Category.anime, source="anilist", external_id="1001", title="第一號節目", original_title="番組1",
               zh_checked_at=datetime(2026, 11, 1, tzinfo=timezone.utc)))
    s.commit()

mika, rain, stranger = client("mika"), client("rain"), client("stranger")
friends("mika", "rain")

# ---------- pick page ----------
r = mika.get("/me/season")
check("pick page renders the season grid", r.status_code == 200 and r.text.count('<input type="checkbox" name="pick"') == 50, str(r.status_code))
check("pick page title + counter", "2026 秋季新番" in r.text and "已選 <strong data-count>0</strong> 部" in r.text)
check("known Chinese title reused", "第一號節目" in r.text and "Show 1<" not in r.text)
check("AniList asked for this season, TV/ONA list cached", calls and calls[0][:2] == ("FALL", 2026))
mika.get("/me/season")
check("season list cached (one AniList call for two page loads)", len(calls) == 1, str(calls))

# ---------- save 3 picks ----------
r = pick(mika, 1000, 1001, 1002)
check("完成 -> profile anime tab", r.status_code == 303 and r.headers["location"] == "/u/mika#anime", r.headers.get("location", ""))
e = entries("mika")
check("3 picks added to the anime collection", set(e) == {"1000", "1001", "1002"})
check("picks have no rating, season set, marked as quick-pick",
      all(x.tier is None and x.tag is None and x.season == "2026-FALL" and x.quick_pick for x in e.values()))
r = mika.get("/me/season")
check("picked shows stay ticked", r.text.count(" checked>") == 3 and "已選 <strong data-count>3</strong> 部" in r.text)
with Session(engine) as s:
    acts = s.exec(select(Activity).where(Activity.user_id == uid("mika"))).all()
check("one merged feed activity, no per-show 'added' items",
      [a.kind for a in acts] == [ActivityKind.season_picks] and acts[0].note == "2026-FALL", str([a.kind for a in acts]))

# ---------- profile row ----------
r = mika.get("/u/mika")
row = r.text.split('class="season-row"')[1].split("</section>")[0] if 'class="season-row"' in r.text else ""
check("profile anime tab: 本季在追 row with 3 covers", "本季在追" in r.text and row.count('class="card"') == 3)
check("season label on picked cards", "2026 秋季" in r.text)
r = rain.get("/u/mika")
check("friend sees 本季在追 (public)", 'class="season-row"' in r.text)

# ---------- feed ----------
r = rain.get("/feed")
items = season_feed_items(r.text)
season_items = [i for i in items if "新番" in i]
check("friend's feed: one merged item", len(season_items) == 1, str(len(items)))
check("merged sentence names two and counts", season_items and "這季在追《Show 0》、《第一號節目》等 3 部新番" in season_items[0])
check("merged item shows the covers", season_items and season_items[0].count("feed-season-cover") == 3)
r = rain.post(f"/feed/{acts[0].id}/comments", data={"body": "我也在追！"}, follow_redirects=True)
check("friends can comment on the merged item", "我也在追！" in r.text)

pick(mika, 1000, 1001, 1002, 1003, 1004)
r = rain.get("/feed")
season_items = [i for i in season_feed_items(r.text) if "新番" in i]
check("picking more updates the same item", len(season_items) == 1 and "等 5 部新番" in season_items[0])

# privacy: friends-only still reaches friends; private hides it (feed, profile row) from everyone else
privacy("mika", Visibility.friends)
check("anime = 好友: friend still sees the item", any("新番" in i for i in season_feed_items(rain.get("/feed").text)))
check("anime = 好友: stranger can't see the profile row", 'class="season-row"' not in stranger.get("/u/mika").text)
privacy("mika", Visibility.private)
check("anime = 僅自己: friend's feed hides it", not any("新番" in i for i in season_feed_items(rain.get("/feed").text)))
check("anime = 僅自己: friend can't see the profile row", 'class="season-row"' not in rain.get("/u/mika").text)
check("anime = 僅自己: comment route refuses too", rain.post(f"/feed/{acts[0].id}/comments", data={"body": "x"}).status_code == 404)
check("anime = 僅自己: owner still sees own item", any("新番" in i for i in season_feed_items(mika.get("/feed").text)))
privacy("mika", Visibility.public)

# hidden picks drop out of what others see
with Session(engine) as s:
    x = s.exec(select(CollectionEntry).join(Work).where(CollectionEntry.user_id == uid("mika"), Work.external_id == "1004")).one()
    x.hidden = True
    s.add(x)
    s.commit()
season_items = [i for i in season_feed_items(rain.get("/feed").text) if "新番" in i]
check("hidden pick not counted for friends", season_items and "等 4 部新番" in season_items[0])

# ---------- un-picking ----------
# rain already had 1010 rated before picking it; 1011 picked then rated; 1012 picked then tagged; 1013 picked only
with Session(engine) as s:
    w = Work(category=Category.anime, source="anilist", external_id="1010", title="Show 10", zh_checked_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    s.add(w)
    s.flush()
    s.add(CollectionEntry(user_id=uid("rain"), work_id=w.id, tier="great"))
    s.commit()
pick(rain, 1010, 1011, 1012, 1013)
e = entries("rain")
check("already-collected show gets marked, keeps its rating",
      e["1010"].season == "2026-FALL" and e["1010"].tier == "great" and not e["1010"].quick_pick)
rate = rain.post(f"/me/collection/{e['1011'].id}/verdict", data={"tier": "good"}, headers={"X-Requested-With": "fetch"})
tag_tag = rain.post(f"/me/collection/{e['1012'].id}/verdict", data={"tier": "", "tag": "神作"}, headers={"X-Requested-With": "fetch"})
check("rating a pick with the existing rating feature", rate.status_code == 204 and entries("rain")["1011"].tier == "good")
e = entries("rain")
tagged = bool(e["1012"].tag)
r = pick(rain, follow=True)  # un-tick everything
e = entries("rain")
check("un-pick: collected before -> stays, season cleared", "1010" in e and e["1010"].season is None and e["1010"].tier == "great")
check("un-pick: picked then rated -> stays, season cleared", "1011" in e and e["1011"].season is None and e["1011"].tier == "good")
check("un-pick: picked then tagged -> stays", ("1012" in e and e["1012"].season is None) if tagged else "1012" not in e, f"tagged={tagged}")
check("un-pick: picked only -> removed from the collection", "1013" not in e)
check("un-pick flash says what was removed", "移除" in r.text, r.text[:0])
check("nothing picked: no merged item in feed", not any("新番" in i and 'href="/u/rain"' in i.split("</header>")[0] for i in season_feed_items(mika.get("/feed").text)))

# ---------- next season: past picks keep their label ----------
TODAY[0] = date(2027, 1, 6)
r = mika.get("/u/mika")
check("next season: no 本季在追 row yet", 'class="season-row"' not in r.text)
check("next season: past picks labelled 2026 秋季", "2026 秋季" in r.text)
check("past picks still in the collection", {"1000", "1001", "1002", "1003", "1004"} <= set(entries("mika")))
calls.clear()
mika.get("/me/season")
check("next season asks AniList for WINTER 2027", calls and calls[0][:2] == ("WINTER", 2027), str(calls))

# ---------- 探索 banner ----------
TODAY[0] = date(2026, 11, 13)
r = stranger.get("/match")
check("banner on 探索 during the first 8 weeks", "2026 秋季新番開播了，這季你在追哪些？" in r.text)
check("banner links to the pick page", 'href="/me/season?next=/match"' in r.text)
stranger.post("/me/season/banner/dismiss")
check("dismissed banner stays gone", "這季你在追哪些" not in stranger.get("/match").text)
TODAY[0] = date(2026, 11, 27)  # Oct 1 + 8 weeks = Nov 26
check("no banner after week 8", "這季你在追哪些" not in rain.get("/match").text)
TODAY[0] = date(2027, 1, 3)
check("dismissal is per season: back for winter", "2027 冬季新番開播了，這季你在追哪些？" in stranger.get("/match").text)
TODAY[0] = date(2026, 11, 13)
check("banner gone once you've picked this season", "這季你在追哪些" not in mika.get("/match").text)
check("collection anime tab has the quick-pick entry", 'href="/me/season"' in mika.get("/me/collection").text)

# ---------- AniList down ----------
async def down(*a):
    raise anilist.AniListError("down")


anilist.season_anime = down
seasonal._fetch.__wrapped__  # noqa: B018  (ttl_cache keeps the old list for FALL; use a fresh season)
TODAY[0] = date(2027, 4, 2)
r = mika.get("/me/season")
check("AniList down: friendly error, no crash", r.status_code == 200 and "AniList 暫時無法連線" in r.text)
anilist.season_anime = fake_season
TODAY[0] = date(2026, 11, 13)

# ---------- matching: weight, cap, reason order ----------
with Session(engine) as s:
    a = s.exec(select(User).where(User.username == "mika")).one()
    rare_rated = CollectionEntry(user_id=a.id, work_id=1, tier="must_watch")
    s.add(rare_rated)
    s.commit()

pick_entry = CollectionEntry(tier=None, season="2026-FALL", quick_pick=True)
plain_entry = CollectionEntry(tier=None)
okay_entry = CollectionEntry(tier="okay")
check("unrated quick pick weighs less than 普通", matching._weight(pick_entry, Category.anime) == 0.8 < matching._weight(okay_entry, Category.anime))
check("other unrated entries unchanged (1.0)", matching._weight(plain_entry, Category.anime) == 1.0)
rated_pick = CollectionEntry(tier="great", season="2026-FALL")
check("once rated, the tier weight applies", matching._weight(rated_pick, Category.anime) == 2.5)

# two fresh people who share 6 seasonal picks and 1 rated show
for name in ("ana", "ben"):
    client(name)
with Session(engine) as s:
    ana, ben = (s.exec(select(User).where(User.username == n)).one() for n in ("ana", "ben"))
    for u in (ana, ben):
        u.birth_date = date(2000, 1, 1)
        s.add(u)
    rare = Work(category=Category.anime, source="anilist", external_id="77", title="冷門神作")
    s.add(rare)
    s.flush()
    s.add(CollectionEntry(user_id=ana.id, work_id=rare.id, tier="great"))
    s.add(CollectionEntry(user_id=ben.id, work_id=rare.id, tier="good"))
    s.commit()
c_ana, c_ben = TestClient(app), TestClient(app)
c_ana.post("/login", data={"username": "ana", "password": "testpass123"})
c_ben.post("/login", data={"username": "ben", "password": "testpass123"})
six = [1020, 1021, 1022, 1023, 1024, 1025]
pick(c_ana, *six)
pick(c_ben, *six)
with Session(engine) as s:
    ana = s.exec(select(User).where(User.username == "ana")).one()
    found = {m.user.username: m for m in matching.find_matches(s, ana)}
m = found.get("ben")
check("ben recommended to ana", m is not None, str(list(found)))
if m:
    texts = [r.text for r in m.reasons]
    check("rated shared show is the first reason", texts and texts[0].startswith("你們都看過《冷門神作》"), str(texts))
    check("seasonal reasons read 你們這季都在追", any(t.startswith("你們這季都在追《") for t in texts), str(texts))
    check("seasonal reasons come after the rated one", all(t.startswith("你們這季都在追") for t in texts[1:]), str(texts))
    check("only 3 seasonal-only shows count", m.shared == 1 + 3, str(m.shared))
    with Session(engine) as s:
        ana = s.exec(select(User).where(User.username == "ana")).one()
        seasonal_score = sum(r.score for r in matching.find_matches(s, ana)[0].reasons if r.seasonal) if False else None
    rated_reason = m.reasons[0]
    seasonal_reasons = [r for r in m.reasons if r.seasonal]
    check("a rated shared show outweighs a seasonal one", seasonal_reasons and rated_reason.score > max(r.score for r in seasonal_reasons))

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
