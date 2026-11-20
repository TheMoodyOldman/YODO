"""Shared exact-match book import; new entries always require privacy review."""
import hashlib
import json
import unicodedata
from sqlmodel import Session, select
from app.models import Category, CollectionEntry, User, Work

def normalized(value: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def import_books(session: Session, user: User, rows: list[dict], *, source: str) -> tuple[int, int]:
    # Reuse exact title + author across metadata providers. Never guess from a fuzzy search.
    existing = session.exec(select(Work).where(Work.category == Category.book)).all()
    by_name = {(normalized(w.title), normalized(w.creator or '')): w for w in existing}
    by_provider = {(w.source, w.external_id): w for w in existing}
    owned = {e.work_id for e in session.exec(select(CollectionEntry).where(CollectionEntry.user_id == user.id))}
    added = skipped = 0
    for row in rows:
        key = (normalized(row['title']), normalized(row['author']))
        provider_id = row.get('provider_id')
        work = by_provider.get((source, provider_id)) if provider_id else None
        work = work or by_name.get(key)
        if work is None:
            identity = json.dumps(key, ensure_ascii=False).encode('utf-8')
            work = Work(category=Category.book, source=source, external_id=row.get('provider_id') or hashlib.sha256(identity).hexdigest(),
                        title=row['title'], creator=row['author'] or None,
                        cover_url=row.get('cover_url') or (f"https://covers.openlibrary.org/b/isbn/{row['isbn']}-M.jpg?default=false" if row.get('isbn') else None),
                        year=row.get('year'))
            session.add(work); session.flush(); by_name[key] = work
            by_provider[(work.source, work.external_id)] = work
        if work.id in owned:
            skipped += 1
            continue
        session.add(CollectionEntry(user_id=user.id, work_id=work.id, status=row['status'], pending_review=True))
        owned.add(work.id); added += 1
    session.commit()
    return added, skipped
