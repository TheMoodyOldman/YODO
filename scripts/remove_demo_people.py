"""Remove the `demo_` fake people (from scripts.seed_demo) from a database, together with everything
that points at them: collection entries, friendships, activities and their comments, messages, game
rooms they host, and so on (followed through the foreign keys). Shared works stay.

Only usernames starting with `demo_` are touched; the `demo` account itself is kept.
Dry run by default; add --apply to delete. Back the database up first.
Usage: .venv\\Scripts\\python.exe -m scripts.remove_demo_people [--apply]
"""

import sys

from sqlalchemy import delete, select
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401  register tables
from app.config import settings
from app.db import engine
from app.models import User

PREFIX = "demo_"


def doomed_rows(session: Session, user_ids: set[int]) -> dict[str, set]:
    """Primary keys to delete per table: the users, then every row whose foreign key points at a
    row already being deleted, repeated until nothing new turns up."""
    tables = SQLModel.metadata.sorted_tables
    doomed: dict[str, set] = {"user": set(user_ids)}
    changed = True
    while changed:
        changed = False
        for table in tables:
            if table.name == "user":
                continue
            pk = list(table.primary_key.columns)[0]
            for column in table.columns:
                for fk in column.foreign_keys:
                    target = fk.column.table.name
                    if not doomed.get(target):
                        continue
                    ids = set(session.execute(select(pk).where(column.in_(doomed[target]))).scalars())
                    new = ids - doomed.setdefault(table.name, set())
                    if new:
                        doomed[table.name] |= new
                        changed = True
    return {name: ids for name, ids in doomed.items() if ids}


def main(apply: bool) -> int:
    with Session(engine) as session:
        users = session.exec(select(User).where(User.username.startswith(PREFIX))).scalars().all()
        users = [u for u in users if u.username.startswith(PREFIX)]  # LIKE treats "_" as a wildcard
        print(f"database: {settings.database_url}")
        if not users:
            print(f"no {PREFIX} accounts")
            return 0
        print("accounts:", ", ".join(f"{u.username} ({u.display_name})" for u in users))
        doomed = doomed_rows(session, {u.id for u in users})
        for name, ids in doomed.items():
            print(f"  {name}: {len(ids)} rows")
        if not apply:
            print("dry run: nothing deleted (add --apply)")
            return 0
        by_name = {t.name: t for t in SQLModel.metadata.sorted_tables}
        for table in reversed(SQLModel.metadata.sorted_tables):  # children before parents
            ids = doomed.get(table.name)
            if ids:
                pk = list(table.primary_key.columns)[0]
                session.execute(delete(by_name[table.name]).where(pk.in_(ids)))
        session.commit()
        print("deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv[1:]))
