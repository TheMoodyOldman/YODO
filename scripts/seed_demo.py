"""Build the demo database (demo.db) from scratch, for the 複賽 demo:

- account `demo`: rated anime, Steam-style games with monthly hours, songs with monthly plays
  (so Recap has something to show), and 本季新番 picks;
- 24 `demo_` fake people (scripts.demo_people), each with a bio, friends-only contacts, two illustrated
  photos, some private categories, and anime, films, books, games and songs to their own taste;
  2 of them are demo's friends (feed, messages), 3 have sent demo a friend request, the rest are
  strangers for 探索; all can log in with the demo password. Plus a short chat between demo and 小雨;
- the caches a demo needs filled in advance: this season's list with Chinese titles, and song
  previews for 猜歌, so the demo doesn't wait on AniList, Bangumi or iTunes.

It writes the snapshot demo.seed.db and copies it to demo.db; `python -m scripts.reset_demo` later
restores demo.db from that snapshot without the network. Real data (app.db) is never touched.
Needs the network. Usage: .venv\\Scripts\\python.exe -m scripts.seed_demo [--finish]
(--finish: the accounts are already built; only redo previews, genres, work pages and covers)
"""

import os

from scripts import demo_db

if __name__ == "__main__":  # before any app import: the app reads DATABASE_URL once
    os.environ["DATABASE_URL"] = demo_db.SNAPSHOT_URL

import asyncio  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import secrets  # noqa: E402
import socket  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

import httpx  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from sqlmodel import Session, col, select  # noqa: E402

from app import anime_search, card_render, catalog, genres, photos, quickpick, seasonal, workinfo  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.models import (  # noqa: E402
    Category, CollectionEntry, FriendStatus, Friendship, Message, MonthlyPlays, MonthlyPlaytime, User, Visibility, Work,
    utcnow,
)
from app.privacy import set_privacy  # noqa: E402
from app.services import anilist, books, itunes, lastfm, tmdb  # noqa: E402
from app.services.steam import ASSET_URL  # noqa: E402
from scripts import demo_people  # noqa: E402

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-123"
DEMO_ANIME = [("Frieren", "must_watch"), ("Bocchi the Rock", "great"), ("Mob Psycho 100", "good"), ("Cowboy Bebop", None)]
# Steam games: (appid, name, hours last month, hours this month, earlier hours)
DEMO_GAMES = [
    (1245620, "艾爾登法環", 14, 22, 84),
    (413150, "星露谷物語", 6, 11, 68),
    (1145360, "Hades", 4, 9, 27),
    (367520, "窟窿騎士", 2, 5, 28),
]
# Songs: (artist, title, plays last month, plays this month)
DEMO_SONGS = [
    ("YOASOBI", "夜に駆ける", 18, 26),
    ("ヨルシカ", "ただ君に晴れ", 12, 21),
    ("結束バンド", "青春コンプレックス", 9, 19),
    ("Official髭男dism", "Pretender", 10, 12),
    ("米津玄師", "Lemon", 7, 9),
    ("告五人", "披星戴月的想你", 5, 8),
]
# 小雨 shares some of demo's songs (and has a few of her own), so 猜歌對戰 has a fair mix.
RAIN_SONGS = [("YOASOBI", "夜に駆ける", 20), ("結束バンド", "青春コンプレックス", 15), ("Aimer", "残響散歌", 22),
              ("LiSA", "紅蓮華", 11), ("ヨルシカ", "ただ君に晴れ", 6)]
CHAT = [  # (from demo?, text, minutes ago)
    (False, "你也在追藥屋第三季！這季貓貓也太可愛", 95),
    (True, "對啊，每週六晚上準時開看 😆", 90),
    (False, "要不要一起玩猜歌？我最近都在聽結束バンド", 30),
    (True, "好啊，等等開房間邀你！", 26),
]

# 本季新番 picks are indexes into this season's AniList list (most popular first), so the demo works
# whatever the season. Fake people: (username, name, bio, region, friend of demo?, picks, tiers for DEMO_ANIME)
DEMO_PICKS = [0, 1, 3, 6]
# 本季新番 shows Bangumi has no Chinese name for: their usual Taiwanese titles (AniList id -> title).
ZH_OVERRIDES = {
    195539: "電馭叛客：邊緣行者 2",
    195604: "黑色五葉草 第二季",
    159042: "轉生就是劍 第二季",
    210482: "JOJO的奇妙冒險 STEEL BALL RUN",
    191788: "青之蘆葦 第二季",
    209872: "亂馬½ 第三季",
    198727: "千歲同學在彈珠汽水瓶裡 第二季",
    176314: "佐佐木與文鳥小嗶 第二季",
    178868: "魔法騎士雷阿斯",
}
FAKE_PEOPLE = [
    ("demo_rain", "小雨", "每季必追新番，週末補番到天亮", "台北市", True, [0, 1, 2, 4, 7], {"Frieren": "must_watch"}),
    ("demo_zhe", "阿哲", "熱血番和機器人派", "台中市", True, [1, 3, 5], {"Mob Psycho 100": "great"}),
    ("demo_hikari", "小光", "日常系、音樂番都愛，想找人一起聊", "新北市", False, [0, 3, 6, 8, 9], {"Bocchi the Rock": "must_watch", "Frieren": "great"}),
    ("demo_nana", "奈奈", "冷門番挖掘中", "高雄市", False, [2, 6, 10, 11], {"Cowboy Bebop": "great"}),
    # 20 more strangers for 探索: overlaps with demo range from strong (shared rated anime, the same
    # games and songs) to none, so recommendations show a real spread instead of four people.
    ("demo_mochi", "麻糬", "星露谷種田中，週末想找人一起開農場", "台南市", False, [0, 4], {"Frieren": "great"}),
    ("demo_kai", "阿凱", "魂系受苦愛好者，交界地死了三百次", "桃園市", False, [1, 5], {"Mob Psycho 100": "good"}),
    ("demo_yuki", "雪乃", "J-POP 重度使用者，YOASOBI 每首都會唱", "台北市", False, [0, 2, 6], {"Bocchi the Rock": "great"}),
    ("demo_bean", "豆豆", "下班就是要玩 Hades 一輪", "新竹市", False, [3], {}),
    ("demo_lulu", "露露", "演唱會常客，想找一起排隊的朋友", "台中市", False, [0, 1], {"Bocchi the Rock": "must_watch"}),
    ("demo_ken", "Ken", "經典番收藏家，星際牛仔看了五遍", "新北市", False, [6, 10], {"Cowboy Bebop": "must_watch", "Frieren": "good"}),
    ("demo_cat", "貓咪隊長", "養貓、彈吉他、聽樂團", "高雄市", False, [2, 7], {"Bocchi the Rock": "great"}),
    ("demo_jun", "小俊", "RPG 和策略遊戲，最近在玩柏德之門 3", "台北市", False, [5, 9], {}),
    ("demo_mei", "小美", "週末補番、平日通勤聽歌", "彰化縣", False, [0, 1, 3], {"Frieren": "must_watch"}),
    ("demo_hao", "阿豪", "Minecraft 建築派，也玩泰拉瑞亞", "台中市", False, [4], {}),
    ("demo_sora", "空", "Vaundy 和 King Gnu 的粉，求同好", "新北市", False, [1, 8], {"Mob Psycho 100": "great"}),
    ("demo_pudding", "布丁", "雙人遊戲找隊友中，一起玩雙人成行吧", "桃園市", False, [0, 3], {"Frieren": "great"}),
    ("demo_wen", "小文", "台灣獨立樂團愛好者，草東、落日飛車必聽", "台南市", False, [], {}),
    ("demo_leo", "Leo", "什麼都玩一點，找人聊天", "宜蘭縣", False, [2, 4, 6], {"Mob Psycho 100": "good", "Cowboy Bebop": "good"}),
    ("demo_ivy", "Ivy", "治癒系動畫和療癒遊戲", "花蓮縣", False, [0, 6], {"Frieren": "must_watch", "Bocchi the Rock": "great"}),
    ("demo_tom", "湯姆", "殺戮尖塔一千小時，卡牌遊戲同好來", "新竹縣", False, [7], {}),
    ("demo_ann", "安安", "華語流行和周杰倫，偶爾看動畫", "嘉義市", False, [1], {}),
    ("demo_rex", "雷克斯", "魔物獵人老獵人，徵四人隊", "高雄市", False, [3, 5, 11], {"Mob Psycho 100": "must_watch"}),
    ("demo_hana", "花子", "動畫歌曲收藏中，最愛 LiSA 和 Aimer", "台北市", False, [0, 1, 2], {"Frieren": "great", "Bocchi the Rock": "good"}),
    ("demo_owen", "歐文", "剛開始玩 Undertale，求不劇透", "屏東縣", False, [8], {}),
]
# Every fake person can log in with the demo password (on a second phone, for 猜歌對戰, 猜誰是臥底,
# messages and friend requests). They only exist in demo.db, never in real data (app.db).
LOGIN_PEOPLE = {p[0] for p in FAKE_PEOPLE}
# What each person is looking for (app.matching.LOOKING_FOR keys).
LOOKING = {
    "demo_rain": "anime,music", "demo_zhe": "game,anime", "demo_hikari": "anime,music,chat", "demo_nana": "anime,chat",
    "demo_mochi": "game,chat", "demo_kai": "game", "demo_yuki": "music,live", "demo_bean": "game",
    "demo_lulu": "live,music", "demo_ken": "anime", "demo_cat": "music,chat", "demo_jun": "game,chat",
    "demo_mei": "anime,music", "demo_hao": "game", "demo_sora": "music,live", "demo_pudding": "game,chat",
    "demo_wen": "music,live", "demo_leo": "chat", "demo_ivy": "anime,game", "demo_tom": "game",
    "demo_ann": "music,chat", "demo_rex": "game", "demo_hana": "anime,music", "demo_owen": "game,chat",
}
# New people who have already sent demo a friend request, so 好友邀請 has something to accept.
REQUESTS_TO_DEMO = ["demo_mochi", "demo_yuki", "demo_ivy"]


def _months() -> tuple[str, str]:
    now = datetime.now(TAIPEI)
    last = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return last, now.strftime("%Y-%m")


def _entry(session: Session, user: User, work: Work) -> CollectionEntry:
    entry = session.exec(select(CollectionEntry).where(CollectionEntry.user_id == user.id, CollectionEntry.work_id == work.id)).first()
    if entry is None:
        entry = CollectionEntry(user_id=user.id, work_id=work.id)
        session.add(entry)
        session.flush()
    return entry


def _work(session: Session, source: str, external_id: str, **fields) -> Work:
    work = session.exec(select(Work).where(Work.source == source, Work.external_id == external_id)).first()
    if work is None:  # never rename an existing work (it may be shared with real users)
        work = Work(source=source, external_id=external_id, **fields)
        session.add(work)
        session.flush()
    return work


def _person(session: Session, username: str, name: str, bio: str, region: str) -> User:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:  # anyone outside LOGIN_PEOPLE gets a random password nobody knows
        password = DEMO_PASSWORD if username in LOGIN_PEOPLE else secrets.token_urlsafe(24)
        user = User(username=username, display_name=name, password_hash=hash_password(password),
                    birth_date=date(2001, 5, 5), bio=bio, region=region, looking_for=LOOKING.get(username, "anime"),
                    email=f"{username}@example.com", email_verified_at=utcnow(), tour_state="skipped",
                    onboarding_hidden=True)
        session.add(user)
        session.flush()
    return user


def _befriend(session: Session, a: User, b: User) -> None:
    for x, y in ((a, b), (b, a)):
        row = session.exec(select(Friendship).where(Friendship.requester_id == x.id, Friendship.addressee_id == y.id)).first()
        if row is not None:
            row.status = FriendStatus.accepted
            session.add(row)
            return
    session.add(Friendship(requester_id=a.id, addressee_id=b.id, status=FriendStatus.accepted))


async def _song_cover(client: httpx.AsyncClient, artist: str, title: str) -> str | None:
    await asyncio.sleep(0.8)  # iTunes allows roughly 20 searches a minute before it starts refusing
    try:
        r = await _retrying(lambda: client.get("https://itunes.apple.com/search", params={
            "term": f"{artist} {title}", "entity": "song", "country": "JP", "limit": 1}), title, (httpx.HTTPError,))
        art = (r.json().get("results") or [{}])[0].get("artworkUrl100")
        return art.replace("100x100bb", "600x600bb") if art else None
    except (httpx.HTTPError, ValueError):
        return None


async def seed_music(session: Session, client: httpx.AsyncClient, user: User, songs: list[tuple]) -> None:
    """Songs with monthly plays (Recap, rankings, 猜歌). songs: (artist, title, plays...) per month, oldest first."""
    if not songs:
        return
    months = _months()[-(len(songs[0]) - 2):]
    for artist, title, *plays in songs:
        key = lastfm.song_key(artist, title)
        work = session.exec(select(Work).where(Work.source == "lastfm", Work.external_id == key)).first()
        if work is None:
            work = _work(session, "lastfm", key, category=Category.music, title=title, creator=artist,
                         cover_url=await _song_cover(client, artist, title))
        entry = _entry(session, user, work)
        for month, n in ((m, n) for m, n in zip(months, plays) if n):
            if not session.exec(select(MonthlyPlays).where(
                    MonthlyPlays.user_id == user.id, MonthlyPlays.work_id == work.id, MonthlyPlays.month == month)).first():
                session.add(MonthlyPlays(user_id=user.id, work_id=work.id, month=month, plays=n))
        entry.play_count = sum(plays)
        session.add(entry)
    session.commit()


def seed_person_games(session: Session, user: User, games: list[tuple[int, str, int, int]]) -> None:
    """A fake person's Steam games: (appid, name, total hours, hours this month)."""
    this = _months()[1]
    for appid, name, total_h, this_h in games:
        work = _work(session, "steam", str(appid), category=Category.game, title=name,
                     cover_url=f"{ASSET_URL}/{appid}/library_600x900.jpg")
        entry = _entry(session, user, work)
        if this_h and not session.exec(select(MonthlyPlaytime).where(
                MonthlyPlaytime.user_id == user.id, MonthlyPlaytime.work_id == work.id, MonthlyPlaytime.month == this)).first():
            session.add(MonthlyPlaytime(user_id=user.id, work_id=work.id, month=this,
                                        start_minutes=(total_h - this_h) * 60, end_minutes=total_h * 60))
        entry.playtime_minutes = total_h * 60
        session.add(entry)
    session.commit()


def request_friendship(session: Session, sender: User, recipient: User) -> None:
    """A pending request from sender, unless the two already have one either way."""
    if session.exec(select(Friendship).where(
            ((Friendship.requester_id == sender.id) & (Friendship.addressee_id == recipient.id))
            | ((Friendship.requester_id == recipient.id) & (Friendship.addressee_id == sender.id)))).first():
        return
    session.add(Friendship(requester_id=sender.id, addressee_id=recipient.id, status=FriendStatus.pending))
    session.commit()


# ---------- riding out Wi-Fi drops: wait for the network instead of losing the lookup ----------

NET_HOSTS = ("graphql.anilist.co", "store.steampowered.com", "itunes.apple.com", "api.themoviedb.org")


def _online() -> bool:
    for host in NET_HOSTS:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            continue
    return False


async def wait_for_network() -> None:
    """Return at once when online; otherwise print a note and check every 15 s until the network is back."""
    if await asyncio.to_thread(_online):
        return
    print("  ⚠ 網路斷線了（getaddrinfo failed），等網路恢復後自動繼續…", flush=True)
    waited = 0
    while not await asyncio.to_thread(_online):
        await asyncio.sleep(15)
        waited += 15
        if waited % 120 == 0:
            print(f"  …還在等網路（{waited // 60} 分鐘）", flush=True)
    print("  ✓ 網路恢復，繼續", flush=True)


async def _retrying(call, label: str, errors: tuple = (Exception,), attempts: int = 4):
    """call() with retries: after a failure, wait for the network (and a little longer each time)."""
    for attempt in range(attempts):
        try:
            return await call()
        except errors as e:
            if attempt == attempts - 1:
                raise
            retry_after = getattr(e, "retry_after", None)
            await wait_for_network()
            await asyncio.sleep(retry_after + 1 if retry_after else 3 * (attempt + 1))
    raise AssertionError("unreachable")


# ---------- the fake people's profiles and collections (scripts.demo_people) ----------

async def _anime_work(session: Session, cache: dict[str, Work | None], query: str) -> Work | None:
    """The anime AniList finds first for `query`, with its Chinese title; looked up once per query."""
    if query in cache:
        return cache[query]
    work = None
    try:
        results = await _retrying(lambda: anilist.search_anime(query), query, (anilist.AniListError,))
    except anilist.AniListError as e:
        print(f"AniList unavailable for {query}: {e}")
        return None  # not cached: a later person may find it
    if results:
        a = results[0]
        work = session.exec(select(Work).where(Work.source == "anilist", Work.external_id == str(a.id))).first()
        if work is None:
            zh = await anime_search.chinese_title(a.original_title)
            work = _work(session, "anilist", str(a.id), category=Category.anime, title=zh or a.title,
                         original_title=a.original_title, cover_url=a.cover_url, year=a.year, zh_checked_at=utcnow())
            await asyncio.sleep(anime_search.BANGUMI_DELAY)
    cache[query] = work
    return work


async def _book_work(session: Session, cache: dict[str, Work | None], query: str) -> Work | None:
    """The first book Google Books / Open Library finds for `query`; looked up once per query."""
    if query in cache:
        return cache[query]
    work = None
    try:
        found = await _retrying(lambda: books.search(query), query, (books.BooksError,))
    except books.BooksError as e:
        print(f"book search unavailable for {query}: {e}")
        return None  # not cached: a later person may find it
    if found:
        b = found[0]
        work = _work(session, b.source, b.external_id, category=Category.book, title=b.title,
                     creator=b.authors or None, cover_url=b.cover_url, year=b.year)
    await asyncio.sleep(0.5)  # gentle on Open Library
    cache[query] = work
    return work


async def _film_work(session: Session, key: str) -> Work:
    """A film or series by TMDB id: TMDB's own title and poster when TMDB_API_KEY is set, else ours."""
    zh, original, year = demo_people.FILMS[key]
    title = None
    if tmdb.configured():
        try:
            title = await _retrying(lambda: tmdb.get_title(key), key, (tmdb.TmdbError,))
        except tmdb.TmdbError as e:
            print(f"TMDB unavailable for {key}: {e}")
    if title:
        return _work(session, "tmdb", key, category=Category.film, title=title.title or zh,
                     original_title=title.original_title, cover_url=title.cover_url, year=title.year)
    return _work(session, "tmdb", key, category=Category.film, title=zh,
                 original_title=original if original != zh else None, year=year)


async def _film_search(session: Session, cache: dict, query: str, kind: str) -> Work | None:
    """The first live-action TMDB result for `query` (needs TMDB_API_KEY); looked up once per query."""
    if (query, kind) in cache:
        return cache[(query, kind)]
    work = None
    if tmdb.configured():
        try:
            found = [t for t in await _retrying(lambda: tmdb.search(query, prefer=kind), query, (tmdb.TmdbError,))
                     if not t.is_anime]
        except tmdb.TmdbError as e:
            print(f"TMDB unavailable for {query}: {e}")
            return None  # not cached: a later person may find it
        if found:
            t = found[0]
            work = _work(session, "tmdb", t.external_id, category=Category.film, title=t.title,
                         original_title=t.original_title, cover_url=t.cover_url, year=t.year)
        await asyncio.sleep(0.25)
    cache[(query, kind)] = work
    return work


STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/"


async def _steam_find(client: httpx.AsyncClient, cache: dict, name: str) -> tuple[int, str] | None:
    """(appid, Chinese store name) of the first Steam store result for `name`; looked up once per name."""
    if name in cache:
        return cache[name]
    async def lookup():
        r = await client.get(STEAM_SEARCH, params={"term": name, "l": "tchinese", "cc": "TW"})
        if r.status_code == 429:
            raise httpx.HTTPError("Steam rate limit")
        return r.json()

    try:
        data = await _retrying(lookup, name, (httpx.HTTPError, ValueError), attempts=5)
    except (httpx.HTTPError, ValueError) as e:
        print(f"Steam store unavailable for {name}: {e}")
        return None  # not cached: a later person may find it
    items = [i for i in data.get("items", []) if i.get("type") == "app" and i.get("id")]
    found = (int(items[0]["id"]), items[0]["name"]) if items else None
    await asyncio.sleep(0.4)
    cache[name] = found
    return found


def _rate(session: Session, user: User, work: Work | None, tier: str | None, tag: str | None,
          status: str | None = None) -> None:
    if work is None:
        return
    entry = _entry(session, user, work)
    entry.tier = entry.tier or tier
    entry.tag = entry.tag or tag
    if status:
        entry.status = status
    session.add(entry)


def profile_photos(name: str, tagline: str, palette: tuple[str, str]) -> list[bytes]:
    """Two illustrated 4:5 cards (no real faces): the name's first character, and the person's tagline."""
    images = []
    for i, text in enumerate(([name[:1]], [name, tagline])):
        top, bottom = palette if i == 0 else palette[::-1]
        img = Image.new("RGB", photos.SIZE, top)
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = photos.SIZE
        c1, c2 = Image.new("RGB", (1, 1), top).getpixel((0, 0)), Image.new("RGB", (1, 1), bottom).getpixel((0, 0))
        for y in range(h):  # vertical gradient
            t = y / h
            draw.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)))
        for k, (cx, cy, r) in enumerate(((0.15, 0.2, 260), (0.9, 0.75, 340), (0.7, 0.1, 140), (0.2, 0.9, 180))):
            draw.ellipse([cx * w - r, cy * h - r, cx * w + r, cy * h + r], fill=(255, 255, 255, 28 + 10 * (k % 2)))
        if i == 0:
            f = card_render.font("bold", 460)
            draw.text((w / 2, h / 2), text[0], font=f, fill=(255, 255, 255, 235), anchor="mm")
        else:
            draw.text((w / 2, h * 0.42), text[0], font=card_render.font("bold", 150), fill=(255, 255, 255, 240), anchor="mm")
            draw.text((w / 2, h * 0.58), text[1], font=card_render.font("regular", 72), fill=(255, 255, 255, 220), anchor="mm")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=88)
        images.append(out.getvalue())
    return images


async def seed_profiles(session: Session, client: httpx.AsyncClient, people: dict[str, User],
                        demo_works: dict[str, Work]) -> None:
    """Bios, contacts, privacy, photos and the five collections of every fake person.

    Each collection follows demo_people.plan() (30+ per category); when a lookup finds nothing, the next
    items from demo_people.spare() fill the gap so nobody ends up under demo_people.MIN_PER_CATEGORY."""
    anime_cache: dict[str, Work | None] = dict(demo_works)  # demo's anime, already looked up by the same query
    book_cache: dict[str, Work | None] = {}
    film_cache: dict = {}
    steam_cache: dict = {}
    counts = {"anime": 0, "films": 0, "books": 0, "games": 0, "songs": 0}
    total = len(demo_people.PROFILES)
    for n, (username, p) in enumerate(demo_people.PROFILES.items(), 1):
        user = people.get(username)
        if user is None:
            continue
        print(f"  [{n}/{total}] {username} ({user.display_name})…", flush=True)
        user.bio = p["bio"]
        contacts = {k: {"v": v, "vis": "friends"} for k, v in p["contacts"].items()}  # app.contacts format
        user.contacts = json.dumps(contacts) if contacts else None
        session.add(user)
        for category, visibility in p["privacy"].items():
            set_privacy(session, user.id, Category(category), Visibility(visibility))
        if not photos.photo_ids(session, user.id):
            for data in profile_photos(user.display_name, p["tagline"], p["palette"]):
                photos.add_photo(session, user, data)

        plan = demo_people.plan(username)
        mine = {k: set() for k in counts}

        async def add_anime(item) -> None:
            query, tier, tag = item
            work = await _anime_work(session, anime_cache, query)
            if work and work.id not in mine["anime"]:
                mine["anime"].add(work.id)
                _rate(session, user, work, tier, tag)

        async def add_film(item) -> None:
            how, tier, tag = item
            if how[0] == "tmdb":
                work = await _film_work(session, how[1])
            else:
                work = await _film_search(session, film_cache, how[1], how[2])
            if work and work.id not in mine["films"]:
                mine["films"].add(work.id)
                _rate(session, user, work, tier, tag)

        async def add_book(item) -> None:
            query, status, tier, tag = item
            work = await _book_work(session, book_cache, query)
            if work and work.id not in mine["books"]:
                mine["books"].add(work.id)
                _rate(session, user, work, tier, tag, status)

        games: list[tuple[int, str, int, int]] = []

        async def add_game(item) -> None:
            how, total_h, this_h = item
            found = (how[1], demo_people.GAMES[how[1]]) if how[0] == "appid" else await _steam_find(client, steam_cache, how[1])
            if found and found[0] not in mine["games"]:
                mine["games"].add(found[0])
                games.append((found[0], found[1], total_h, this_h))

        for category, add in (("anime", add_anime), ("films", add_film), ("books", add_book), ("games", add_game)):
            for item in plan[category]:
                await add(item)
            for item in demo_people.spare(username, category):
                if len(mine[category]) >= demo_people.MIN_PER_CATEGORY:
                    break
                await add(item)
            session.commit()
        seed_person_games(session, user, games)
        await seed_music(session, client, user, plan["songs"])
        mine["songs"] = set(range(len(plan["songs"])))
        for k in counts:
            counts[k] += len(mine[k])
        print("      " + ", ".join(f"{len(mine[k])} {k}" for k in counts), flush=True)
    print("fake people's collections: " + ", ".join(f"{n} {k}" for k, n in counts.items()))


def seed_games(session: Session, user: User) -> None:
    last, this = _months()
    for appid, name, h_last, h_this, h_before in DEMO_GAMES:
        work = _work(session, "steam", str(appid), category=Category.game, title=name,
                     cover_url=f"{ASSET_URL}/{appid}/library_600x900.jpg")
        entry = _entry(session, user, work)
        before, mid, total = h_before * 60, (h_before + h_last) * 60, (h_before + h_last + h_this) * 60
        for month, start, end in ((last, before, mid), (this, mid, total)):
            if not session.exec(select(MonthlyPlaytime).where(
                    MonthlyPlaytime.user_id == user.id, MonthlyPlaytime.work_id == work.id, MonthlyPlaytime.month == month)).first():
                session.add(MonthlyPlaytime(user_id=user.id, work_id=work.id, month=month, start_minutes=start, end_minutes=end))
        entry.playtime_minutes = total
        session.add(entry)
    session.commit()


def seed_chat(session: Session, demo: User, friend: User) -> None:
    if session.exec(select(Message).where(col(Message.sender_id).in_([demo.id, friend.id]),
                                          col(Message.recipient_id).in_([demo.id, friend.id]))).first():
        return
    now = utcnow()
    for from_demo, text, ago in CHAT:
        a, b = (demo, friend) if from_demo else (friend, demo)
        when = now - timedelta(minutes=ago)
        session.add(Message(sender_id=a.id, recipient_id=b.id, body=text, created_at=when, read_at=when))
    session.commit()


async def seed_season(session: Session, demo: User, demo_works: dict[str, Work]) -> dict[str, User]:
    people = {}
    key = seasonal.current_key()
    try:  # the whole list with Chinese titles goes into the cache, so the pick page works offline
        count = await seasonal.prefetch(session, key)
        cached, fetched_at = catalog.get(session, seasonal._cache_key(key))
        for item in cached:
            if not item.get("zh") and item["id"] in ZH_OVERRIDES:
                item["zh"] = ZH_OVERRIDES[item["id"]]
        catalog.put(session, seasonal._cache_key(key), cached, fetched_at=fetched_at)
        listed = await seasonal.season_list(session, key, warm=False)
        print(f"本季新番 list cached: {count} shows")
    except anilist.AniListError as e:
        print(f"AniList unavailable, skipped 本季新番 picks: {e}")
        listed = []
    shows = dict(enumerate(listed))

    if shows:
        seasonal.save(session, demo, key, [shows[i] for i in DEMO_PICKS if i in shows])
    for username, name, bio, region, friend, picks, tiers in FAKE_PEOPLE:
        person = people[username] = _person(session, username, name, bio, region)
        if friend:
            _befriend(session, demo, person)
        for query, tier in tiers.items():  # a rated classic shared with demo
            work = demo_works.get(query)
            if work and not session.exec(select(CollectionEntry).where(
                    CollectionEntry.user_id == person.id, CollectionEntry.work_id == work.id)).first():
                session.add(CollectionEntry(user_id=person.id, work_id=work.id, tier=tier))
        session.commit()
        if shows:
            seasonal.save(session, person, key, [shows[i] for i in picks if i in shows])
    print(f"本季新番 ({seasonal.label(key)}): demo + {len(FAKE_PEOPLE)} fake people seeded")
    return people


async def seed_anime(session: Session, user: User) -> dict[str, Work]:
    """demo's rated anime, with Chinese titles. Existing works keep their titles."""
    demo_works: dict[str, Work] = {}
    for query, tier in DEMO_ANIME:
        results = await anilist.search_anime(query)
        if not results:
            continue
        a = results[0]
        work = session.exec(select(Work).where(Work.source == "anilist", Work.external_id == str(a.id))).first()
        if work is None:
            zh = await anime_search.chinese_title(a.original_title)
            work = _work(session, "anilist", str(a.id), category=Category.anime, title=zh or a.title,
                         original_title=a.original_title, cover_url=a.cover_url, year=a.year, zh_checked_at=utcnow())
            await asyncio.sleep(anime_search.BANGUMI_DELAY)
        entry = _entry(session, user, work)
        if tier and not entry.tier:
            entry.tier = tier
            session.add(entry)
        demo_works[query] = work
    session.commit()
    return demo_works


async def seed_previews(session: Session) -> None:
    """Look up iTunes previews for every demo song now, so 猜歌對戰 starts without waiting on iTunes.

    When iTunes starts refusing (HTTP 403/429 several times in a row) the rest is skipped instead of
    waiting it out: those songs stay unchecked, and `python -m scripts.fill_previews` fills them later."""
    found, refused = 0, 0
    todo = session.exec(select(Work).where(Work.category == Category.music, col(Work.preview_checked_at).is_(None))).all()
    for n, work in enumerate(todo, 1):
        await wait_for_network()
        try:
            work.preview_url = await itunes.find_preview(work.creator or "", work.title)
        except itunes.ItunesUnavailable as e:
            refused += 1
            print(f"iTunes unavailable for {work.title}: {e}")
            if refused >= 5:
                print(f"⚠ iTunes 暫時封鎖了查詢，先跳過剩下 {len(todo) - n} 首的試聽。"
                      "跑完後過 30 分鐘以上，再執行 python -m scripts.fill_previews 補上。")
                break
            await asyncio.sleep(10)
            continue
        refused = 0
        work.preview_checked_at = utcnow()
        found += bool(work.preview_url)
        session.add(work)
        session.commit()
        await asyncio.sleep(1.5)  # stay under iTunes' limit
    session.commit()
    print(f"song previews: {found} found")


async def main(finish: bool = False) -> None:
    """finish=True (--finish): keep the accounts and collections already in demo.seed.db and only
    redo the steps after them (previews, genres, work pages, copying to demo.db, covers)."""
    if finish:
        import sqlite3

        try:
            with sqlite3.connect(demo_db.SNAPSHOT) as con:
                done = con.execute("SELECT 1 FROM catalogcache WHERE key = ?", (demo_db.SEEDED_AT_KEY,)).fetchone()
        except sqlite3.DatabaseError:
            done = None
        if not done:
            print("demo.seed.db 還沒建完帳號和收藏，請改跑完整的 python -m scripts.seed_demo")
            return
        print("--finish: 保留已建好的帳號和收藏，只跑後面的步驟")
    else:
        demo_db.remove(demo_db.SNAPSHOT)  # always build from scratch
        init_db()
        async with httpx.AsyncClient(timeout=10) as client:
            await _seed(client)
    with Session(engine) as session:
        await seed_previews(session)
        # Do the background job's work now (genres for 風格偏好, Chinese titles), so the demo
        # server has nothing to look up while presenting: no network, no competing writes.
        print("looking up genres…", flush=True)
        while True:  # a batch that fails because the Wi-Fi dropped is simply tried again
            await wait_for_network()
            if not await genres.enrich_batch(session) and await asyncio.to_thread(_online):
                break
        while True:
            await wait_for_network()
            if not await anime_search.enrich_titles(session) and await asyncio.to_thread(_online):
                break
        print("caching work pages…", flush=True)
        # Work pages' facts and big covers, so opening one during the demo needs no network.
        works = session.exec(select(Work)).all()
        filled = 0
        for work in works:
            await wait_for_network()
            filled += (await workinfo.cache_work_info(session, work)) != workinfo.WorkInfo()
            await asyncio.sleep(0.5)  # gentle on AniList / Steam / Last.fm
        print(f"work pages cached: {filled} / {len(works)}")
        # 新手教學 cover picker: every tab's popular list cached ahead (built-in lists cover failures)
        for cat in quickpick.CATEGORIES:
            try:
                print(f"popular {cat.value}: {await quickpick.prefetch(session, cat)} items")
            except Exception as e:  # the page falls back to its built-in list
                print(f"popular {cat.value}: not cached ({e})")
    engine.dispose()  # release the snapshot file before copying it
    demo_db.restore()
    print(f"Seeded /u/{DEMO_USERNAME}: {demo_db.SNAPSHOT.name} built and copied to {demo_db.DEMO_DB.name}")
    # local copies of every cover and preview, for a demo without the network (LOCAL_ASSETS_DIR)
    from scripts import cache_covers

    await wait_for_network()
    got, had, failed = await cache_covers.download(cache_covers.collect_urls(demo_db.SNAPSHOT), cache_covers.DEFAULT_DIR)
    print(f"covers/previews in {cache_covers.DEFAULT_DIR.name}/: {got} downloaded, {had} already there, {len(failed)} failed")


async def _seed(client: httpx.AsyncClient) -> None:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == DEMO_USERNAME)).first()
        if user is None:
            user = User(
                username=DEMO_USERNAME,
                display_name="Demo",
                bio="週末追番，通勤聽 city pop",
                region="台中市",
                looking_for="anime,music,game",
                password_hash=hash_password(DEMO_PASSWORD),
                birth_date=date(2000, 1, 1),
                email="demo@example.com",  # reserved test domain; marked verified so no e-mail banner
                email_verified_at=utcnow(),
                tour_state="skipped",  # the tour can still be restarted from 設定
                onboarding_hidden=True,  # no 新手教學 card on the profile / feed during a demo
            )
            session.add(user)
            session.flush()

        demo_works = await seed_anime(session, user)
        seed_games(session, user)
        await seed_music(session, client, user, DEMO_SONGS)
        people = await seed_season(session, user, demo_works)
        rain = people.get("demo_rain")
        if rain:
            await seed_music(session, client, rain, [(a, t, 0, n) for a, t, n in RAIN_SONGS])
            seed_chat(session, user, rain)
        await seed_profiles(session, client, people, demo_works)
        for username in REQUESTS_TO_DEMO:
            if username in people:
                request_friendship(session, people[username], user)
        print(f"{len(REQUESTS_TO_DEMO)} friend requests waiting for demo")
        # reset_demo moves every timestamp forward by (reset time - this), so "1 小時前" stays true
        catalog.put(session, demo_db.SEEDED_AT_KEY, {"note": "when demo.seed.db was built"})


if __name__ == "__main__":
    import sys

    asyncio.run(main(finish="--finish" in sys.argv[1:]))
