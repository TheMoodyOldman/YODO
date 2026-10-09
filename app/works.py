from sqlmodel import Session, select

from app.models import Category, Work


def upsert_work(
    session: Session,
    *,
    category: Category,
    source: str,
    external_id: str,
    title: str,
    original_title: str | None = None,
    creator: str | None = None,
    cover_url: str | None = None,
    year: int | None = None,
) -> Work:
    """Get the Work for (source, external_id), refreshing its metadata, or create it."""
    work = session.exec(select(Work).where(Work.source == source, Work.external_id == external_id)).first()
    if work is None:
        work = Work(category=category, source=source, external_id=external_id, title=title)
    work.title = title
    work.original_title = original_title
    work.creator = creator
    work.cover_url = cover_url
    work.year = year
    session.add(work)
    session.flush()
    return work
