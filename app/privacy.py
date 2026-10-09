from sqlmodel import Session, select

from app.models import Category, CategoryPrivacy, User, Visibility


def get_privacy(session: Session, user_id: int) -> dict[Category, Visibility]:
    rows = session.exec(select(CategoryPrivacy).where(CategoryPrivacy.user_id == user_id)).all()
    privacy = {c: Visibility.public for c in Category}
    privacy.update({row.category: row.visibility for row in rows})
    return privacy


def set_privacy(session: Session, user_id: int, category: Category, visibility: Visibility) -> None:
    row = session.exec(
        select(CategoryPrivacy).where(CategoryPrivacy.user_id == user_id, CategoryPrivacy.category == category)
    ).first()
    if row is None:
        row = CategoryPrivacy(user_id=user_id, category=category)
    row.visibility = visibility
    session.add(row)


def can_view(visibility: Visibility, owner: User, viewer: User | None) -> bool:
    if viewer is not None and viewer.id == owner.id:
        return True
    # No friend system until phase 2, so "friends" behaves like "private" for now.
    return visibility == Visibility.public
