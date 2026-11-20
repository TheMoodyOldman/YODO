"""Import only book metadata extracted locally from a Kobo bookshelf."""
import hashlib
import json
import re
import unicodedata

from sqlmodel import Session, select
from app.models import Category, CollectionEntry, User, Work

MAX_BOOKS = 5000
MAX_PAYLOAD = 900_000


class KoboFormatError(ValueError):
    pass


def normalized(value: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def parse_metadata(payload: str) -> list[dict]:
    if len(payload.encode('utf-8')) > MAX_PAYLOAD:
        raise KoboFormatError('書單太大，請分批匯入（每批最多 5000 本）。')
    try:
        data = json.loads(payload)
    except (ValueError, RecursionError) as e:
        raise KoboFormatError('無法讀取書單，請重新選取 Kobo 書櫃檔案。') from e
    if not isinstance(data, dict) or data.get('format') != 'yodo-kobo-v1' or not isinstance(data.get('books'), list):
        raise KoboFormatError('書單格式不正確。')
    if len(data['books']) > MAX_BOOKS:
        raise KoboFormatError('每次最多匯入 5000 本。')
    found = {}
    rank = {'want': 0, 'reading': 1, 'read': 2}
    for item in data['books']:
        if not isinstance(item, dict):
            raise KoboFormatError('書籍資料格式不正確。')
        title, author = item.get('title'), item.get('author', '')
        status = item.get('status', 'reading')
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise KoboFormatError('書名不可空白或超過 500 字。')
        if not isinstance(author, str) or len(author) > 300 or not isinstance(status, str) or status not in rank:
            raise KoboFormatError('作者或閱讀狀態格式不正確。')
        title, author = title.strip(), author.strip()
        isbn = item.get('isbn', '')
        isbn = re.sub(r'[-\s]', '', isbn) if isinstance(isbn, str) else ''
        if not re.fullmatch(r'(?:\d{13}|\d{9}[\dXx])', isbn):
            isbn = ''
        key = (normalized(title), normalized(author))
        row = {'title': title, 'author': author, 'status': status, 'isbn': isbn}
        if key not in found or rank[status] > rank[found[key]['status']]:
            found[key] = row
    return list(found.values())


def parse_text(text: str, status: str) -> list[dict]:
    if len(text.encode('utf-8')) > MAX_PAYLOAD:
        raise KoboFormatError('書單太大，請分批貼上。')
    rows = []
    for line in text.splitlines():
        if line.strip():
            title, _, author = line.strip().partition('\t')
            rows.append({'title': title, 'author': author, 'status': status})
    return parse_metadata(json.dumps({'format': 'yodo-kobo-v1', 'books': rows}, ensure_ascii=False))


def import_books(session: Session, user: User, rows: list[dict]) -> tuple[int, int]:
    # Reuse exact title + author across metadata providers. Never guess from a fuzzy search.
    existing = session.exec(select(Work).where(Work.category == Category.book)).all()
    by_name = {(normalized(w.title), normalized(w.creator or '')): w for w in existing}
    owned = {e.work_id for e in session.exec(select(CollectionEntry).where(CollectionEntry.user_id == user.id))}
    added = skipped = 0
    for row in rows:
        key = (normalized(row['title']), normalized(row['author']))
        work = by_name.get(key)
        if work is None:
            identity = json.dumps(key, ensure_ascii=False).encode('utf-8')
            work = Work(category=Category.book, source='kobo', external_id=hashlib.sha256(identity).hexdigest(),
                        title=row['title'], creator=row['author'] or None,
                        cover_url=f"https://covers.openlibrary.org/b/isbn/{row['isbn']}-M.jpg?default=false" if row['isbn'] else None)
            session.add(work); session.flush(); by_name[key] = work
        if work.id in owned:
            skipped += 1
            continue
        session.add(CollectionEntry(user_id=user.id, work_id=work.id, status=row['status'], pending_review=True))
        owned.add(work.id); added += 1
    session.commit()
    return added, skipped
