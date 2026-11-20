"""新手教學 cover picker: popular titles per category to tick, plus search, saved as unrated
"quick pick" collection entries (same rules as 本季新番: un-ticking an untouched pick removes it).

Popular lists live in the database cache (catalogcache "popular:<cat>", filled by `prefetch`,
which scripts.seed_demo runs and the background refreshes weekly). A page load never waits on an
API: without a cached list it shows the built-in list below, so a tab is never empty.

喜歡的歌手 are music works with source "artist" (one per artist name). They are not songs: rankings,
Recap and the mini games skip them; matching counts them only as a shared artist.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import Session, select

from app import anime_search, catalog, seasonal
from app.config import settings
from app.models import CatalogCache, Category, CollectionEntry, User, Work
from app.services import books, tmdb
from app.services import popular_sources as src

log = logging.getLogger(__name__)

ARTIST = "artist"  # Work.source for a 喜歡的歌手 pick
BOOKLIST = "booklist"  # Work.source for a built-in book the book search couldn't match (title + author only)
CATEGORIES = (Category.anime, Category.game, Category.music, Category.book, Category.film)
LIST_MAX_AGE = timedelta(days=7)

# ---------- built-in lists (fallbacks; the games list is the list) ----------

# Names as the Steam store shows them in Traditional Chinese (fetched from store.steampowered.com
# appdetails?l=tchinese on 2026-11-20); some official names are English.
GAMES = [
    (1245620, "艾爾登法環"), (2358720, "黑神話：悟空"), (1086940, "柏德之門3"), (413150, "Stardew Valley"),
    (1145360, "Hades"), (367520, "Hollow Knight"), (292030, "巫師3：狂獵 — 重製版"), (1174180, "Red Dead Redemption 2"),
    (271590, "Grand Theft Auto V 傳承版"), (730, "Counter-Strike 2"), (570, "Dota 2"), (578080, "PUBG: BATTLEGROUNDS"),
    (1172470, "《Apex 英雄》"), (1623730, "Palworld / 幻獸帕魯"), (105600, "Terraria"), (1091500, "Cyberpunk 2077"),
    (814380, "Sekiro™: Shadows Die Twice - GOTY Edition"), (374320, "DARK SOULS™ III"), (1145350, "Hades II"),
    (2379780, "Balatro"), (1794680, "Vampire Survivors"), (553850, "HELLDIVERS™ 2"), (2050650, "Resident Evil 4"),
    (582010, "Monster Hunter: World"), (2246340, "Monster Hunter Wilds"), (1203220, "NARAKA: BLADEPOINT"),
    (588650, "Dead Cells"), (268910, "Cuphead"), (504230, "Celeste"), (1817070, "Marvel’s Spider-Man Remastered"),
]
ANIME = [  # AniList id, title (fallback only: no covers)
    (154587, "葬送的芙莉蓮"), (130003, "孤獨搖滾！"), (16498, "進擊的巨人"), (101922, "鬼滅之刃"), (113415, "咒術迴戰"),
    (127230, "鏈鋸人"), (140960, "SPY×FAMILY 間諜家家酒"), (150672, "【我推的孩子】"), (21519, "你的名字。"),
    (21827, "紫羅蘭永恆花園"), (9253, "命運石之門"), (20464, "排球少年！！"), (101348, "冰海戰記"),
    (153518, "迷宮飯"), (21507, "靈能百分百"), (1, "星際牛仔"),
]
ARTISTS = [
    "周杰倫", "五月天", "蔡依林", "告五人", "鄧紫棋", "林俊傑", "草東沒有派對", "落日飛車", "YOASOBI", "ヨルシカ",
    "米津玄師", "Official髭男dism", "Aimer", "LiSA", "King Gnu", "Ado", "BTS", "BLACKPINK", "NewJeans", "IU",
    "Taylor Swift", "The Weeknd", "Ed Sheeran", "Billie Eilish",
]
BOOKS = [  # (title, author): looked up with the existing book search when prefetching
    ("三體", "劉慈欣"), ("活著", "余華"), ("射鵰英雄傳", "金庸"), ("涼宮春日的憂鬱", "谷川流"), ("傾城之戀", "張愛玲"),
    ("那些年，我們一起追的女孩", "九把刀"), ("撒哈拉的故事", "三毛"), ("目送", "龍應台"), ("單車失竊記", "吳明益"),
    ("紅樓夢", "曹雪芹"), ("解憂雜貨店", "東野圭吾"), ("白夜行", "東野圭吾"), ("嫌疑犯X的獻身", "東野圭吾"),
    ("挪威的森林", "村上春樹"), ("1Q84", "村上春樹"), ("人間失格", "太宰治"), ("你的名字。", "新海誠"),
    ("小王子", "聖修伯里"), ("哈利波特：神秘的魔法石", "J.K. 羅琳"), ("魔戒首部曲：魔戒現身", "托爾金"),
    ("福爾摩斯探案全集", "柯南·道爾"), ("一九八四", "喬治·歐威爾"), ("百年孤寂", "馬奎斯"), ("追風箏的孩子", "胡賽尼"),
    ("82年生的金智英", "趙南柱"), ("被討厭的勇氣", "岸見一郎"), ("原子習慣", "詹姆斯·克利爾"), ("人類大歷史", "哈拉瑞"),
    ("我可能錯了", "林德布勞"), ("蛤蟆先生去看心理師", "戴博德"),
]
FILMS = [  # TMDB id, title (fallback only)
    ("movie:496243", "寄生上流"), ("movie:129", "神隱少女"), ("movie:157336", "星際效應"), ("movie:27205", "全面啟動"),
    ("movie:299534", "復仇者聯盟：終局之戰"), ("tv:66732", "怪奇物語"), ("tv:1396", "絕命毒師"), ("tv:93405", "魷魚遊戲"),
    ("tv:76479", "黑袍糾察隊"), ("tv:1399", "冰與火之歌：權力遊戲"),
]


@dataclass
class Item:
    cat: Category
    source: str
    external_id: str
    title: str
    sub: str = ""
    cover_url: str | None = None
    year: int | None = None
    original_title: str | None = None

    @property
    def key(self) -> str:
        return f"{self.cat.value}|{self.source}|{self.external_id}"

    def dump(self) -> dict:
        return {"cat": self.cat.value, "source": self.source, "external_id": self.external_id, "title": self.title,
                "sub": self.sub, "cover_url": self.cover_url, "year": self.year, "original_title": self.original_title}

    @classmethod
    def load(cls, d: dict) -> "Item":
        return cls(Category(d["cat"]), d["source"], d["external_id"], d["title"], d.get("sub") or "",
                   d.get("cover_url"), d.get("year"), d.get("original_title"))


def artist_id(name: str) -> str:
    return name.casefold().strip()


def _fallback(cat: Category) -> list[Item]:
    if cat == Category.game:
        return [Item(cat, "steam", str(a), n, cover_url=src.steam_cover(a)) for a, n in GAMES]
    if cat == Category.anime:
        return [Item(cat, "anilist", str(a), n) for a, n in ANIME]
    if cat == Category.music:
        return [Item(cat, ARTIST, artist_id(n), n, sub="歌手") for n in ARTISTS]
    if cat == Category.book:  # no id until looked up: resolved with the book search when saved
        return [Item(cat, "lookup", f"{t}／{a}", t, sub=a) for t, a in BOOKS]
    return [Item(cat, "tmdb", i, t) for i, t in FILMS]


# ---------- popular lists ----------

def _cache_key(cat: Category) -> str:
    return f"popular:{cat.value}"


async def _fetch(session: Session, cat: Category) -> list[Item]:
    """The live list for a category (network). Raises src.PopularError / others on failure."""
    if cat == Category.game:
        return _fallback(cat)  # curated on purpose (official Steam names); see GAMES
    if cat == Category.anime:
        items = []
        for a in await src.anilist_popular(30):
            zh = await anime_search.chinese_title(a.original_title)
            await asyncio.sleep(anime_search.BANGUMI_DELAY)
            items.append(Item(cat, "anilist", str(a.id), zh or a.title, cover_url=a.cover_url, year=a.year,
                              original_title=a.original_title))
        return items
    if cat == Category.music:
        try:
            chart = await src.lastfm_top_artists()
        except src.PopularError:
            chart = []
        names = list(dict.fromkeys(ARTISTS + chart))[:36]  # local favourites first, then the TW chart
        items = []
        for name in names:
            try:
                hits = await src.deezer_artists(name, 3)
            except src.PopularError:
                hits = []
            hit = next((h for h in hits if h["name"].casefold() == name.casefold()), hits[0] if hits else None)
            items.append(Item(cat, ARTIST, artist_id(name), name, sub="歌手", cover_url=hit and hit["cover_url"]))
            await asyncio.sleep(0.2)
        return items
    if cat == Category.book:
        items = []
        for title, author in BOOKS:
            try:
                found = await books.search(f"{title} {author}")
            except books.BooksError:
                found = []
            b = _book_match(title, found)
            items.append(Item(cat, b.source, b.external_id, title, sub=author, cover_url=b.cover_url, year=b.year)
                         if b else Item(cat, "lookup", f"{title}／{author}", title, sub=author))
            await asyncio.sleep(0.3)
        return items
    return [Item(cat, "tmdb", t.external_id, t.title, sub=t.kind_label, cover_url=t.cover_url, year=t.year,
                 original_title=t.original_title) for t in await src.tmdb_trending()]


async def prefetch(session: Session, cat: Category) -> int:
    """Fetch a category's list now and keep it (seed_demo, weekly background refresh)."""
    items = await _fetch(session, cat)
    catalog.put(session, _cache_key(cat), [i.dump() for i in items])
    return len(items)


_refreshing: set[Category] = set()


async def _refresh(cat: Category) -> None:
    from app.db import engine

    try:
        with Session(engine) as session:
            await prefetch(session, cat)
    except Exception:  # best effort: the built-in list keeps the page usable
        log.exception("popular list refresh failed for %s", cat)
    finally:
        _refreshing.discard(cat)


async def popular(session: Session, cat: Category) -> list[Item]:
    """The tab's list from the cache (no waiting on APIs); built-in list when nothing is cached.
    Missing or week-old lists are refreshed in the background."""
    row = session.get(CatalogCache, _cache_key(cat))
    cached = catalog.get(session, _cache_key(cat)) if row is not None else None
    stale = row is None or catalog._age(row) > LIST_MAX_AGE
    if stale and settings.background_jobs and cat not in _refreshing:
        _refreshing.add(cat)
        asyncio.get_running_loop().create_task(_refresh(cat))
    items = [Item.load(d) for d in cached[0]] if cached else _fallback(cat)
    if cat == Category.anime:  # this season first
        try:
            season = await seasonal.season_list(session, seasonal.current_key(), warm=False)
        except Exception:
            season = []
        seen = {i.external_id for i in items}
        items = [Item(cat, "anilist", str(a.id), a.title, sub="本季", cover_url=a.cover_url, year=a.year,
                      original_title=a.original_title) for a in season[:18] if str(a.id) not in seen] + items
    return items


# ---------- search ----------

async def search(session: Session, cat: Category, query: str) -> list[Item]:
    """Live search for a tab (needs the network). Results are remembered so a pick can be saved
    from server-side data only. Raises src.PopularError when the source is unreachable."""
    query = query.strip()[:80]
    if not query:
        return []
    try:
        if cat == Category.anime:
            found = [Item(cat, "anilist", str(a.id), a.title, cover_url=a.cover_url, year=a.year, original_title=a.original_title)
                     for a in await anime_search.search(query)]
        elif cat == Category.game:
            found = [Item(cat, "steam", g["id"], g["title"], cover_url=g["cover_url"]) for g in await src.steam_search(query)]
        elif cat == Category.music:
            found = [Item(cat, ARTIST, artist_id(a["name"]), a["name"], sub="歌手", cover_url=a["cover_url"])
                     for a in await src.deezer_artists(query)]
        elif cat == Category.book:
            found = [Item(cat, b.source, b.external_id, b.title, sub=b.authors, cover_url=b.cover_url, year=b.year)
                     for b in await books.search(query)]
        else:
            found = [Item(cat, "tmdb", t.external_id, t.title, sub=t.kind_label, cover_url=t.cover_url, year=t.year,
                          original_title=t.original_title) for t in await tmdb.search(query) if not t.is_anime]
    except src.PopularError:
        raise
    except Exception as e:  # AniList / TMDB / book errors look the same to the page
        raise src.PopularError(str(e)) from e
    for item in found:
        catalog.put(session, f"pickitem:{item.key}", item.dump())
    return found


# ---------- saving ----------

def _known(session: Session, key: str) -> Item | None:
    """An item the server produced: a popular list, the season list, a search result or a built-in."""
    cached = catalog.get(session, f"pickitem:{key}")
    if cached:
        return Item.load(cached[0])
    cat = key.split("|", 1)[0]
    try:
        category = Category(cat)
    except ValueError:
        return None
    lists = [catalog.get(session, _cache_key(category)), catalog.get(session, f"season:{seasonal.current_key()}")]
    for found in lists:
        for d in (found[0] if found else []):
            item = Item.load(d) if "cat" in d else Item(Category.anime, "anilist", str(d["id"]), d.get("zh") or d["title"],
                                                         cover_url=d.get("cover_url"), year=d.get("year"),
                                                         original_title=d.get("original_title"))
            if item.key == key:
                return item
    return next((i for i in _fallback(category) if i.key == key), None)


# What may follow a title in an edition's name: 「三體（全球突破…版）」, 「我可能錯了：森林智者…」.
_EDITION_START = tuple("（(：:【〔[－—-")  # not a space: 「被討厭的勇氣 二部曲」 is a sequel


def _book_score(wanted: str, found: str) -> int:
    """2 = the same title, 1 = the same title plus an edition note, 0 = a different book (a study
    of it, a sequel, a summary, a book that merely mentions it in its title...)."""
    from app import zh

    clean = lambda t: zh.to_traditional(t or "").strip().casefold()  # noqa: E731
    bare = lambda t: "".join(ch for ch in clean(t) if ch.isalnum())  # noqa: E731
    a, b = clean(wanted), clean(found)
    if not a:
        return 0
    if bare(wanted) == bare(found):  # same title up to punctuation / script: 「那些年我们一起追的女孩」
        return 2
    return 1 if b.startswith(a) and b[len(a):].startswith(_EDITION_START) else 0


def _book_match(title: str, found: list) -> "books.Book | None":
    """The search hit that really is this book (same title, or an edition of it); among those,
    one with a cover first, then the exact title, then search order."""
    scored = [(not b.cover_url, -s, i) for i, b in enumerate(found) if (s := _book_score(title, b.title))]
    return found[min(scored)[2]] if scored else None


async def _resolve_lookup(item: Item) -> Item:
    """A built-in book without an id yet: the matching book-search record if there is one,
    otherwise the book by title and author alone, so a pick always saves (also offline)."""
    try:
        b = _book_match(item.title, await books.search(f"{item.title} {item.sub}".strip()))
    except books.BooksError:
        b = None
    if b is not None:  # our Traditional Chinese title and author, the record's id and cover
        return Item(item.cat, b.source, b.external_id, item.title, sub=item.sub, cover_url=b.cover_url, year=b.year)
    return Item(item.cat, BOOKLIST, f"{item.title}／{item.sub}", item.title, sub=item.sub)


def _work_for(session: Session, item: Item) -> Work:
    work = session.exec(select(Work).where(Work.source == item.source, Work.external_id == item.external_id)).first()
    if work is None:  # never rename an existing work
        creator = item.title if item.source == ARTIST else (item.sub or None) if item.cat == Category.book else None
        work = Work(category=item.cat, source=item.source, external_id=item.external_id, title=item.title,
                    original_title=item.original_title, creator=creator, cover_url=item.cover_url, year=item.year)
        session.add(work)
        session.flush()
    return work


def entry_keys(session: Session, user: User) -> dict[str, CollectionEntry]:
    """The user's collection keyed like picker items."""
    return {
        f"{w.category.value}|{w.source}|{w.external_id}": e
        for e, w in session.exec(select(CollectionEntry, Work).join(Work).where(CollectionEntry.user_id == user.id))
    }


@dataclass
class SaveResult:
    added: int
    removed: int
    skipped: int  # couldn't be resolved (e.g. a built-in book while the book search is down)


async def save(session: Session, user: User, chosen: list[str], shown: list[str]) -> SaveResult:
    """Add the ticked items; remove untouched quick picks that were shown but un-ticked. Commits."""
    from app.seasonal import is_empty_shell

    have = entry_keys(session, user)
    added = skipped = removed = 0
    for key in dict.fromkeys(chosen):
        if key in have:
            continue
        item = _known(session, key)
        if item is not None and item.source == "lookup":
            item = await _resolve_lookup(item)
            if item.key in have:
                continue
        if item is None:
            skipped += 1
            continue
        work = _work_for(session, item)
        session.add(CollectionEntry(user_id=user.id, work_id=work.id, quick_pick=True))
        have[item.key] = True  # type: ignore[assignment]
        added += 1
    for key in set(shown) - set(chosen):
        entry = have.get(key)
        if isinstance(entry, CollectionEntry) and is_empty_shell(entry) and not entry.season:
            session.delete(entry)
            removed += 1
    session.commit()
    return SaveResult(added, removed, skipped)
