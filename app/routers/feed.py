from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, col, select

from app.auth import RequiredUser
from app.db import SessionDep
from app.models import Activity, CollectionEntry, Comment, User, Visibility, Work
from app.privacy import get_privacy
from app.social import friend_ids
from app import onboarding
from app.templating import flash, render

router = APIRouter()

PAGE_SIZE = 30
SCAN_LIMIT = 300  # recent activities considered per page load (filtering happens in Python)
MAX_COMMENT = 300


@dataclass
class FeedItem:
    activity: Activity
    user: User
    work: Work
    entry: CollectionEntry
    comments: list[tuple[Comment, User]] = field(default_factory=list)


def visible_items(session: Session, viewer: User, activities: list[Activity]) -> list[FeedItem]:
    """Activities the viewer may see: from themselves or friends, in categories shared with
    friends, about entries that are still in the collection and not hidden or awaiting review."""
    friends = friend_ids(session, viewer.id)
    acts = [a for a in activities if a.work_id and (a.user_id == viewer.id or a.user_id in friends)]
    if not acts:
        return []
    user_ids = {a.user_id for a in acts}
    work_ids = {a.work_id for a in acts}
    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(user_ids)))}
    works = {w.id: w for w in session.exec(select(Work).where(col(Work.id).in_(work_ids)))}
    entries = {
        (e.user_id, e.work_id): e
        for e in session.exec(
            select(CollectionEntry).where(col(CollectionEntry.user_id).in_(user_ids), col(CollectionEntry.work_id).in_(work_ids))
        )
    }
    privacy = {uid: get_privacy(session, uid) for uid in user_ids}

    items = []
    for a in acts:
        work, entry = works.get(a.work_id), entries.get((a.user_id, a.work_id))
        if work is None or entry is None or entry.hidden or entry.pending_review:
            continue
        if a.user_id != viewer.id and privacy[a.user_id][work.category] == Visibility.private:
            continue
        items.append(FeedItem(a, users[a.user_id], work, entry))
    return items


def _attach_comments(session: Session, items: list[FeedItem]) -> None:
    by_id = {i.activity.id: i for i in items}
    if not by_id:
        return
    for comment, author in session.exec(
        select(Comment, User)
        .join(User, col(User.id) == Comment.user_id)
        .where(col(Comment.activity_id).in_(by_id))
        .order_by(col(Comment.created_at))
    ):
        by_id[comment.activity_id].comments.append((comment, author))


@router.get("/feed", response_class=HTMLResponse)
def feed(request: Request, session: SessionDep, me: RequiredUser, page: int = 0):
    ids = friend_ids(session, me.id) | {me.id}
    recent = session.exec(
        select(Activity)
        .where(col(Activity.user_id).in_(ids))
        .order_by(col(Activity.updated_at).desc(), col(Activity.id).desc())
        .limit(SCAN_LIMIT)
    ).all()
    items = visible_items(session, me, list(recent))
    page = max(page, 0)
    shown = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    _attach_comments(session, shown)
    return render(
        request,
        "feed.html",
        me=me,
        items=shown,
        page=page,
        has_more=len(items) > (page + 1) * PAGE_SIZE,
        has_friends=len(ids) > 1,
        guide=onboarding.card(session, me),
        friends=sorted(session.exec(select(User).where(col(User.id).in_(ids - {me.id}))).all(), key=lambda u: u.display_name.casefold()),
        MAX_COMMENT=MAX_COMMENT,
    )


@router.post("/feed/{activity_id}/comments")
def add_comment(request: Request, session: SessionDep, me: RequiredUser, activity_id: int, body: Annotated[str, Form()] = ""):
    activity = session.get(Activity, activity_id)
    if activity is None or not visible_items(session, me, [activity]):
        raise HTTPException(status_code=404)
    body = body.strip()
    if not body:
        return RedirectResponse(f"/feed#act-{activity_id}", status_code=303)
    if len(body) > MAX_COMMENT:
        flash(request, f"留言最多 {MAX_COMMENT} 字")
        return RedirectResponse(f"/feed#act-{activity_id}", status_code=303)
    session.add(Comment(activity_id=activity_id, user_id=me.id, body=body))
    session.commit()
    return RedirectResponse(f"/feed#act-{activity_id}", status_code=303)


@router.post("/comments/{comment_id}/delete")
def delete_comment(session: SessionDep, me: RequiredUser, comment_id: int):
    comment = session.get(Comment, comment_id)
    activity = session.get(Activity, comment.activity_id) if comment else None
    if comment is None or activity is None or me.id not in (comment.user_id, activity.user_id):
        raise HTTPException(status_code=404)
    session.delete(comment)
    session.commit()
    return RedirectResponse(f"/feed#act-{activity.id}", status_code=303)
