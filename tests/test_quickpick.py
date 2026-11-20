"""新手教學 cover picker (/me/start): built-in lists when nothing is cached (never an empty tab),
cached popular lists, search per tab (fake APIs), saving / un-ticking quick picks, the 0.8 weight
for quick picks only, and 喜歡的歌手 (source "artist") kept out of song rankings and mini games."""

import asyncio
import os
import pathlib
import re
from datetime import date

here = pathlib.Path(__file__).parent
db = here / "test_quickpick.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import anime_search, catalog, games, matching, music, onboarding, quickpick, songquiz  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, FriendStatus, Friendship, User, Work  # noqa: E402
from app.services import anilist, books, tmdb  # noqa: E402
from app.services import popular_sources as src  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


init_db()


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": f"{name}@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def uid(name):
    with Session(engine) as s:
        return s.exec(select(User).where(User.username == name)).one().id


def entries(name):
    with Session(engine) as s:
        return {f"{w.category.value}|{w.source}|{w.external_id}": (e, w)
                for e, w in s.exec(select(CollectionEntry, Work).join(Work).where(CollectionEntry.user_id == uid(name)))}


alice = client("alice")

# ---------- page: built-in lists, nothing cached, no network ----------


async def no_network(*a, **k):
    raise AssertionError("the page must not call APIs")


src.anilist_popular = src.lastfm_top_artists = src.deezer_artists = src.tmdb_trending = no_network
r = alice.get("/me/start")
page = r.text
tabs = re.findall(r'role="tab" data-tab="(\w+)"', page)
check("page renders five tabs", r.status_code == 200 and tabs == ["anime", "game", "music", "book", "film"], str(tabs))
grid = lambda cat: page.split(f'id="grid-{cat}"')[1].split("</div>\n    </div>")[0]  # noqa: E731
check("game tab: built-in list with official Steam names", grid("game").count('name="pick"') == 30 and "艾爾登法環" in grid("game")
      and "game|steam|1245620" in grid("game"))
check("music tab: built-in artists", grid("music").count('name="pick"') == 24 and "告五人" in grid("music") and "music|artist|" in grid("music"))
check("book tab: the 30-book list incl. the swaps", grid("book").count('name="pick"') == 30 and "涼宮春日的憂鬱" in grid("book")
      and "我可能錯了" in grid("book") and "天龍八部" not in grid("book") and "窮爸爸" not in grid("book"))
check("anime and film tabs are never empty", grid("anime").count('name="pick"') >= 10 and grid("film").count('name="pick"') >= 8)
check("every tile reports it was shown", page.count('name="shown"') == page.count('name="pick"'))
check("import is a secondary link", "想要更完整？匯入紀錄" in page and 'href="/me/collection"' in page)
check("onboarding step points here", next(s for s in onboarding.steps(Session(engine), Session(engine).get(User, uid("alice"))) if s.key == "collect").href == "/me/start")

# cached popular list is used instead of the built-in one
with Session(engine) as s:
    catalog.put(s, "popular:film", [quickpick.Item(Category.film, "tmdb", "movie:1", "快取的電影", cover_url="https://img.test/f.jpg").dump()])
check("cached popular list replaces the built-in one", "快取的電影" in alice.get("/me/start").text)

# ---------- search (fake APIs) ----------


async def fake_steam(q):
    return [{"id": "999", "title": f"遊戲 {q}", "cover_url": src.steam_cover(999)}]


async def fake_deezer(q, limit=8):
    return [{"name": "宇多田ヒカル", "cover_url": "https://img.test/hikki.jpg"}]


async def fake_books(q):
    if "找不到" in q:
        return []
    return [books.Book(books.OPENLIBRARY, "OL1W", "三體", "劉慈欣", "https://img.test/b.jpg", 2008)]


async def fake_anime(q):
    return [anilist.Anime(5000, "測試動畫", "テスト", None, 2026, "TV")]


async def fake_tmdb(q, prefer=None):
    return [tmdb.Title("tv:5", "測試影集", None, None, 2020, "tv")]


src.steam_search, src.deezer_artists = fake_steam, fake_deezer
books.search, anime_search.search, tmdb.search = fake_books, fake_anime, fake_tmdb
results = {cat: alice.get(f"/me/start/search?cat={cat}&q=測試").json() for cat in ("anime", "game", "music", "book", "film")}
check("search works on every tab", all(r["items"] for r in results.values()), str({k: len(v["items"]) for k, v in results.items()}))
check("music search returns artists", results["music"]["items"][0]["key"] == "music|artist|宇多田ヒカル")


async def down(*a, **k):
    raise src.PopularError("offline")


src.steam_search = down
r = alice.get("/me/start/search?cat=game&q=x").json()
check("search offline: a friendly message, no crash", r["items"] == [] and "暫時無法使用" in r["error"])
check("unknown category rejected", alice.get("/me/start/search?cat=nope&q=x").status_code == 400)

# ---------- saving ----------
picks = ["game|steam|1245620", "music|artist|告五人", "music|artist|宇多田ヒカル", f"book|{books.OPENLIBRARY}|OL1W", "anime|anilist|5000",
         "book|lookup|活著／余華", "film|tmdb|tv:5"]
r = alice.post("/me/start", data={"pick": picks, "shown": picks + ["game|steam|730"], "next": "/u/alice"}, follow_redirects=False)
e = entries("alice")
check("save redirects back", r.status_code == 303 and r.headers["location"] == "/u/alice")
check("ticked items added as unrated quick picks", all(k in e for k in picks[:5] + ["film|tmdb|tv:5"])
      and all(x.quick_pick and not x.tier for x, _ in e.values()), str(sorted(e)))
check("built-in book: an unrelated search hit is not taken as the book", "book|booklist|活著／余華" in e
      and e["book|booklist|活著／余華"][1].title == "活著" and e["book|booklist|活著／余華"][1].creator == "余華", str(sorted(e)))
art = e["music|artist|告五人"][1]
check("favourite artist stored as an artist work", art.category == Category.music and art.creator == "告五人" and art.title == "告五人")
page = alice.get("/me/start").text
check("picked items show ticked, counter counts them", 'value="game|steam|1245620" checked' in page and "已選 <strong data-count>" in page)

books.search = lambda q: fake_books("找不到")
r = alice.post("/me/start", data={"pick": ["book|lookup|紅樓夢／曹雪芹"], "shown": []}, follow_redirects=True)
check("book the search can't find is still saved, by title and author", "book|booklist|紅樓夢／曹雪芹" in entries("alice")
      and "暫時找不到資料" not in r.text)


async def matching_books(q):
    return [books.Book(books.OPENLIBRARY, "OL9W", "白夜行（新版）", "東野圭吾", "https://img.test/w.jpg", 2010)]


books.search = matching_books
alice.post("/me/start", data={"pick": ["book|lookup|白夜行／東野圭吾"], "shown": []})
check("built-in book matched to the real record when the title matches", f"book|{books.OPENLIBRARY}|OL9W" in entries("alice"))
check("matched built-in book keeps the list's Traditional Chinese title", entries("alice")[f"book|{books.OPENLIBRARY}|OL9W"][1].title == "白夜行")

# un-tick: untouched quick picks go, rated ones and non-quick-pick entries stay
with Session(engine) as s:
    x = s.get(CollectionEntry, e["anime|anilist|5000"][0].id)
    x.tier = "great"
    s.add(x)
    w = Work(category=Category.game, source="steam", external_id="730", title="CS2")
    s.add(w)
    s.flush()
    s.add(CollectionEntry(user_id=uid("alice"), work_id=w.id, playtime_minutes=0))  # a Steam import
    s.commit()
shown = picks + ["game|steam|730"]
alice.post("/me/start", data={"pick": [], "shown": shown})
e = entries("alice")
check("un-ticked untouched picks removed", "game|steam|1245620" not in e and "music|artist|告五人" not in e)
check("rated pick and Steam import kept", "anime|anilist|5000" in e and "game|steam|730" in e)
check("imported entry shows as locked (already collected)", 'value="game|steam|730" checked disabled' in alice.get("/me/start").text)

# ---------- weights ----------
CE = CollectionEntry
check("quick-picked game without hours weighs 0.8", matching._weight(CE(quick_pick=True), Category.game) == 0.8)
check("Steam import with 0 hours keeps weight 0", matching._weight(CE(playtime_minutes=0), Category.game) == 0)
check("quick-picked artist / book / film weigh 0.8", all(matching._weight(CE(quick_pick=True), c) == 0.8
                                                       for c in (Category.music, Category.book, Category.film)))
check("once rated or played, the normal weight", matching._weight(CE(quick_pick=True, tier="great"), Category.book) == 2.5
      and matching._weight(CE(quick_pick=True, playtime_minutes=600), Category.game) > 2)

# ---------- 喜歡的歌手 never quiz material ----------
bob = client("bob")
with Session(engine) as s:
    a_id, b_id = uid("alice"), uid("bob")
    for u in (a_id, b_id):
        user = s.get(User, u)
        user.birth_date = date(2000, 1, 1)
        s.add(user)
    s.add(Friendship(requester_id=a_id, addressee_id=b_id, status=FriendStatus.accepted))
    artist = Work(category=Category.music, source="artist", external_id="yoasobi", title="YOASOBI", creator="YOASOBI")
    s.add(artist)
    s.flush()
    for u in (a_id, b_id):
        s.add(CollectionEntry(user_id=u, work_id=artist.id, quick_pick=True))
    for i in range(6):
        song = Work(category=Category.music, source="lastfm", external_id=f"s{i}", title=f"Song {i}", creator="YOASOBI")
        s.add(song)
        s.flush()
        for u in (a_id, b_id):
            s.add(CollectionEntry(user_id=u, work_id=song.id, play_count=3 + i))
    s.commit()
    alice_u, bob_u = s.get(User, a_id), s.get(User, b_id)
    rows = games.visible_rows(s, bob_u, alice_u, True)
    check("guess / compat / bingo rows skip favourite artists", rows and all(w.source != "artist" for _, w in rows))
    tiers = songquiz.candidate_tiers(s, alice_u, bob_u, True)
    check("猜歌 candidates are songs only", tiers and all(w.source != "artist" for tier in tiers for w in tier))
    my_rows = list(s.exec(select(CollectionEntry, Work).join(Work).where(CollectionEntry.user_id == a_id)))
    check("song rankings skip favourite artists", all(w.source != "artist" for _, w in music.top_songs(my_rows, 50)))


async def no_preview(work_artist, title):
    return "https://audio.test/clip.m4a"


from app.services import itunes  # noqa: E402

itunes.find_preview = no_preview
with Session(engine) as s:
    quiz = asyncio.run(songquiz.build_quiz(s, s.get(User, uid("alice")), s.get(User, uid("bob")), True))
check("猜歌 never asks about an artist", quiz and all(rnd["t"].startswith("Song ") for rnd in quiz), str([r["t"] for r in quiz]))
page = alice.get("/u/alice").text
check("profile shows 喜歡的歌手", "喜歡的歌手" in page and "YOASOBI" in page)
coll = alice.get("/me/collection").text
check("collection lists favourite artists apart from songs", "喜歡的歌手" in coll and 'data-title="YOASOBI"' not in coll)

# built-in books: only the book itself (or an edition of it) counts, as seen with Google Books
for wanted, found, ok in [
    ("三體", "三體（全球突破三千萬冊燙銀簽名版）", True), ("我可能錯了", "我可能錯了：森林智者的最後一堂人生課", True),
    ("那些年，我們一起追的女孩", "那些年我们一起追的女孩", True), ("解憂雜貨店", "解憂雜貨店", True),
    ("單車失竊記", "吳明益“單車失竊記”中臺語文化詞英譯的翻譯策略探討", False), ("1Q84", "村上春樹『1Q84』をどう読むか", False),
    ("你的名字。", "你的名字。Another Side:Earthbound", False), ("82年生的金智英", "讓我成為妳：《82年生的金智英》趙南柱作家", False),
    ("原子習慣", "基于詹姆斯•克利尔所著图书 原子习惯", False), ("撒哈拉的故事", "三毛流浪記: 撒哈拉的故事", False),
    ("被討厭的勇氣", "被討厭的勇氣 二部曲完結篇", False),
]:
    check(f"book match {'accepts' if ok else 'rejects'}: {wanted} -> {found[:16]}", bool(quickpick._book_score(wanted, found)) == ok)
hits = [books.Book("googlebooks", "seq", "被討厭的勇氣 二部曲", "岸見一郎", None, 2016),
        books.Book("googlebooks", "ed", "被討厭的勇氣（新版）", "岸見一郎", None, 2020),
        books.Book("googlebooks", "same", "被討厭的勇氣", "岸見一郎", None, 2014)]
check("exact title preferred over an edition, sequels never", quickpick._book_match("被討厭的勇氣", hits).external_id == "same")
hits[1] = books.Book("googlebooks", "ed", "被討厭的勇氣（新版）", "岸見一郎", "https://img.test/c.jpg", 2020)
check("an edition with a cover beats the same title without one", quickpick._book_match("被討厭的勇氣", hits).external_id == "ed")

# a new user who only picked artists: the card shows them, no empty song rankings
carol = client("carol")
carol.post("/me/start", data={"pick": ["music|artist|告五人"], "shown": ["music|artist|告五人"]})
page = carol.get("/u/carol").text
overview = page.split('data-panel="overview"')[1].split('role="tabpanel"')[0]
check("artist-only card: favourite artist in the overview, no empty rankings",
      "告五人" in overview and "最常聽的歌曲" not in page and "最常聽的歌手" not in page)

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
