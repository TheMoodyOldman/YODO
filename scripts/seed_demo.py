"""Create a local demo account with a few anime, plus a few fake people with 本季新番 picks
(2 of them friends with demo for the feed, 2 not, for 探索 recommendations). Development only.

Usage: .venv\\Scripts\\python.exe -m scripts.seed_demo
"""

import asyncio
import secrets
from datetime import date

from sqlmodel import Session, select

from app import anime_search, seasonal
from app.auth import hash_password
from app.db import engine, init_db
from app.models import Category, CollectionEntry, FriendStatus, Friendship, User, Work
from app.services import anilist
from app.works import upsert_work

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-123"
DEMO_ANIME = [("Frieren", 10), ("Bocchi the Rock", 9), ("Mob Psycho 100", 8), ("Cowboy Bebop", None)]

# 本季新番 picks are indexes into this season's AniList list (most popular first), so the demo works
# whatever the season. Fake people: (username, name, bio, region, friend of demo?, picks, tiers for DEMO_ANIME)
DEMO_PICKS = [0, 1, 3, 6]
FAKE_PEOPLE = [
    ("demo_rain", "小雨", "每季必追新番，週末補番到天亮", "台北市", True, [0, 1, 2, 4, 7], {"Frieren": "must_watch"}),
    ("demo_zhe", "阿哲", "熱血番和機器人派", "台中市", True, [1, 3, 5], {"Mob Psycho 100": "great"}),
    ("demo_hikari", "小光", "日常系、音樂番都愛，想找人一起聊", "新北市", False, [0, 3, 6, 8, 9], {"Bocchi the Rock": "must_watch", "Frieren": "great"}),
    ("demo_nana", "奈奈", "冷門番挖掘中", "高雄市", False, [2, 6, 10, 11], {"Cowboy Bebop": "great"}),
]


def _person(session: Session, username: str, name: str, bio: str, region: str) -> User:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:  # fake people can't log in: random password nobody knows
        user = User(username=username, display_name=name, password_hash=hash_password(secrets.token_urlsafe(24)),
                    birth_date=date(2001, 5, 5), bio=bio, region=region, looking_for="anime")
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


async def seed_season(session: Session, demo: User, demo_works: dict[str, Work]) -> None:
    key = seasonal.current_key()
    try:
        listed = await anilist.season_anime(*reversed(seasonal.parse(key)), seasonal.LIST_SIZE)
    except anilist.AniListError as e:
        print(f"AniList unavailable, skipped 本季新番 picks: {e}")
        return
    wanted = sorted({i for i in DEMO_PICKS + [i for p in FAKE_PEOPLE for i in p[5]] if i < len(listed)})
    shows: dict[int, seasonal.SeasonAnime] = {}
    for i in wanted:  # Chinese titles for the shows we use (Bangumi, gently)
        a = listed[i]
        zh = await anime_search.chinese_title(a.original_title)
        seasonal._zh_titles[a.id] = zh
        shows[i] = seasonal.SeasonAnime(a.id, zh or a.title, a.original_title, a.cover_url, a.year, a.format)
        await asyncio.sleep(anime_search.BANGUMI_DELAY)

    seasonal.save(session, demo, key, [shows[i] for i in DEMO_PICKS if i in shows])
    for username, name, bio, region, friend, picks, tiers in FAKE_PEOPLE:
        person = _person(session, username, name, bio, region)
        if friend:
            _befriend(session, demo, person)
        for query, tier in tiers.items():  # a rated classic shared with demo
            work = demo_works.get(query)
            if work and not session.exec(select(CollectionEntry).where(
                    CollectionEntry.user_id == person.id, CollectionEntry.work_id == work.id)).first():
                session.add(CollectionEntry(user_id=person.id, work_id=work.id, tier=tier))
        session.commit()
        seasonal.save(session, person, key, [shows[i] for i in picks if i in shows])
    print(f"本季新番 ({seasonal.label(key)}): demo + {len(FAKE_PEOPLE)} fake people seeded")


async def main() -> None:
    init_db()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == DEMO_USERNAME)).first()
        if user is None:
            user = User(
                username=DEMO_USERNAME,
                display_name="Demo",
                bio="週末追番，通勤聽 city pop",
                password_hash=hash_password(DEMO_PASSWORD),
                birth_date=date(2000, 1, 1),
            )
            session.add(user)
            session.flush()

        demo_works: dict[str, Work] = {}
        for query, rating in DEMO_ANIME:
            existing = session.exec(select(Work).join(CollectionEntry).where(
                CollectionEntry.user_id == user.id, Work.category == Category.anime, Work.source == "anilist")).all()
            results = await anilist.search_anime(query)
            if not results:
                continue
            a = results[0]
            known = next((w for w in existing if w.external_id == str(a.id)), None)
            if known is not None:  # keep its (possibly Chinese) title
                demo_works[query] = known
                continue
            work = upsert_work(
                session,
                category=Category.anime,
                source="anilist",
                external_id=str(a.id),
                title=a.title,
                original_title=a.original_title,
                cover_url=a.cover_url,
                year=a.year,
            )
            entry = session.exec(
                select(CollectionEntry).where(CollectionEntry.user_id == user.id, CollectionEntry.work_id == work.id)
            ).first()
            if entry is None:
                session.add(CollectionEntry(user_id=user.id, work_id=work.id, rating=rating))
            demo_works[query] = work
        session.commit()
        await seed_season(session, user, demo_works)
    print(f"Seeded /u/{DEMO_USERNAME}")


if __name__ == "__main__":
    asyncio.run(main())
