"""Create a local demo account with a few anime, for development only.

Usage: .venv\\Scripts\\python.exe -m scripts.seed_demo
"""

import asyncio
from datetime import date

from sqlmodel import Session, select

from app.auth import hash_password
from app.db import engine, init_db
from app.models import Category, CollectionEntry, User
from app.services import anilist
from app.works import upsert_work

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-123"
DEMO_ANIME = [("Frieren", 10), ("Bocchi the Rock", 9), ("Mob Psycho 100", 8), ("Cowboy Bebop", None)]


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

        for query, rating in DEMO_ANIME:
            results = await anilist.search_anime(query)
            if not results:
                continue
            a = results[0]
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
        session.commit()
    print(f"Seeded /u/{DEMO_USERNAME}")


if __name__ == "__main__":
    asyncio.run(main())
