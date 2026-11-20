from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

if settings.database_url.startswith("sqlite"):
    # Many people at once (live demo): sync routes run on up to 40 threadpool threads and a page
    # can use two connections (the route's and render()'s), so the default pool of 5 + 10 ran out.
    # SQLite connections are cheap. A writer waits up to 15 s for the lock instead of 5 s.
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 15},
                           pool_size=20, max_overflow=80, pool_timeout=60)
else:
    engine = create_engine(settings.database_url)


def _add_missing_columns() -> None:
    """Minimal additive migration: add new nullable model columns to existing tables.

    create_all() only creates missing tables. Anything beyond adding nullable columns
    (renames, type changes, NOT NULL) needs a real migration tool such as Alembic.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    raise RuntimeError(
                        f"Cannot auto-add NOT NULL column {table.name}.{column.name}; "
                        "make it nullable or migrate manually."
                    )
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def init_db() -> None:
    from app import models  # noqa: F401  register tables

    from app.anime import migrate_tags

    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    with engine.begin() as conn:
        migrate_tags(conn)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
