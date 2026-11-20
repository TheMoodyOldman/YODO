"""Build the demo database (demo.db) from scratch, for the 複賽 demo:

- account `demo`: rated anime, Steam-style games with monthly hours, songs with monthly plays
  (so Recap has something to show), and 本季新番 picks;
- a few `demo_` fake people with picks and shared favourites (2 of them friends with demo for the
  feed and messages, 2 not, for 探索 recommendations), plus a short chat between demo and 小雨;
- the caches a demo needs filled in advance: this season's list with Chinese titles, and song
  previews for 猜歌, so the demo doesn't wait on AniList, Bangumi or iTunes.

It writes the snapshot demo.seed.db and copies it to demo.db; `python -m scripts.reset_demo` later
restores demo.db from that snapshot without the network. Real data (app.db) is never touched.
Needs the network. Usage: .venv\\Scripts\\python.exe -m scripts.seed_demo
"""

import os

from scripts import demo_db

if __name__ == "__main__":  # before any app import: the app reads DATABASE_URL once
    os.environ["DATABASE_URL"] = demo_db.SNAPSHOT_URL

import asyncio  # noqa: E402
import secrets  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

import httpx  # noqa: E402
from sqlmodel import Session, col, select  # noqa: E402

from app import anime_search, catalog, genres, quickpick, seasonal, workinfo  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.models import (  # noqa: E402
    Category, CollectionEntry, FriendStatus, Friendship, Message, MonthlyPlays, MonthlyPlaytime, User, Work, utcnow,
)
from app.services import anilist, itunes, lastfm  # noqa: E402
from app.services.steam import ASSET_URL  # noqa: E402

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
# Friends who can log in on a second / third phone (same demo password) for 猜歌對戰 and 猜誰是臥底.
LOGIN_PEOPLE = {"demo_rain", "demo_zhe"}
FAKE_PEOPLE = [
    ("demo_rain", "小雨", "每季必追新番，週末補番到天亮", "台北市", True, [0, 1, 2, 4, 7], {"Frieren": "must_watch"}),
    ("demo_zhe", "阿哲", "熱血番和機器人派", "台中市", True, [1, 3, 5], {"Mob Psycho 100": "great"}),
    ("demo_hikari", "小光", "日常系、音樂番都愛，想找人一起聊", "新北市", False, [0, 3, 6, 8, 9], {"Bocchi the Rock": "must_watch", "Frieren": "great"}),
    ("demo_nana", "奈奈", "冷門番挖掘中", "高雄市", False, [2, 6, 10, 11], {"Cowboy Bebop": "great"}),
]


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
    if user is None:  # others can't log in: random password nobody knows
        password = DEMO_PASSWORD if username in LOGIN_PEOPLE else secrets.token_urlsafe(24)
        user = User(username=username, display_name=name, password_hash=hash_password(password),
                    birth_date=date(2001, 5, 5), bio=bio, region=region, looking_for="anime",
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
    try:
        r = await client.get("https://itunes.apple.com/search",
                             params={"term": f"{artist} {title}", "entity": "song", "country": "JP", "limit": 1})
        art = (r.json().get("results") or [{}])[0].get("artworkUrl100")
        return art.replace("100x100bb", "600x600bb") if art else None
    except (httpx.HTTPError, ValueError):
        return None


async def seed_music(session: Session, client: httpx.AsyncClient, user: User, songs: list[tuple]) -> None:
    """Songs with monthly plays (Recap, rankings, 猜歌). songs: (artist, title, plays...) per month, oldest first."""
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
    """Look up iTunes previews for every demo song now, so 猜歌對戰 starts without waiting on iTunes."""
    found = 0
    for work in session.exec(select(Work).where(Work.category == Category.music, col(Work.preview_checked_at).is_(None))).all():
        try:
            work.preview_url = await itunes.find_preview(work.creator or "", work.title)
        except itunes.ItunesUnavailable as e:
            print(f"iTunes unavailable for {work.title}: {e}")
            continue
        work.preview_checked_at = utcnow()
        found += bool(work.preview_url)
        session.add(work)
    session.commit()
    print(f"song previews: {found} found")


async def main() -> None:
    demo_db.remove(demo_db.SNAPSHOT)  # always build from scratch
    init_db()
    async with httpx.AsyncClient(timeout=10) as client:
        await _seed(client)
    with Session(engine) as session:
        await seed_previews(session)
        # Do the background job's work now (genres for 風格偏好, Chinese titles), so the demo
        # server has nothing to look up while presenting: no network, no competing writes.
        while await genres.enrich_batch(session):
            pass
        while await anime_search.enrich_titles(session):
            pass
        # Work pages' facts and big covers, so opening one during the demo needs no network.
        works = session.exec(select(Work)).all()
        filled = 0
        for work in works:
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
        # reset_demo moves every timestamp forward by (reset time - this), so "1 小時前" stays true
        catalog.put(session, demo_db.SEEDED_AT_KEY, {"note": "when demo.seed.db was built"})


if __name__ == "__main__":
    asyncio.run(main())
