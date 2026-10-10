from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, col, func, or_, select

from app.auth import RequiredUser, is_locked, safe_next
from app.db import SessionDep
from app.models import Block, FriendStatus, Friendship, User, utcnow
from app.social import Relation, get_friendship, is_blocked, relation
from app.templating import flash, render

router = APIRouter()

SEARCH_LIMIT = 20


def _target(session: Session, me: User, username: str) -> User:
    user = session.exec(select(User).where(User.username == username.lower())).first()
    if user is None or user.id == me.id:
        raise HTTPException(status_code=404)
    return user


def _back(next: str, target: User) -> RedirectResponse:
    return RedirectResponse(safe_next(next, f"/u/{target.username}"), status_code=303)


@router.get("/me/friends", response_class=HTMLResponse)
def friends_page(request: Request, session: SessionDep, me: RequiredUser, q: str = ""):
    rows = session.exec(
        select(Friendship).where(or_(col(Friendship.requester_id) == me.id, col(Friendship.addressee_id) == me.id))
    ).all()
    other_ids = {f.addressee_id if f.requester_id == me.id else f.requester_id for f in rows}
    blocked_ids = set(session.exec(select(Block.blocked_id).where(Block.blocker_id == me.id)))
    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(other_ids | blocked_ids)))}

    def people(pred) -> list[User]:
        found = [users[f.addressee_id if f.requester_id == me.id else f.requester_id] for f in rows if pred(f)]
        return sorted(found, key=lambda u: u.display_name.casefold())

    results: list[tuple[User, Relation | None]] = []
    q = q.strip()
    if q:
        pattern = f"%{q.lower()}%"
        matches = session.exec(
            select(User)
            .where(
                or_(func.lower(User.username).like(pattern), func.lower(User.display_name).like(pattern)),
                User.id != me.id,
            )
            .order_by(User.username)
            .limit(SEARCH_LIMIT)
        ).all()
        results = [(u, rel) for u in matches if not is_locked(u) and (rel := relation(session, me, u)) != Relation.blocked]

    return render(
        request,
        "friends.html",
        me=me,
        q=q,
        results=results,
        incoming=people(lambda f: f.status == FriendStatus.pending and f.addressee_id == me.id),
        outgoing=people(lambda f: f.status == FriendStatus.pending and f.requester_id == me.id),
        friends=people(lambda f: f.status == FriendStatus.accepted),
        blocked=sorted((users[i] for i in blocked_ids), key=lambda u: u.display_name.casefold()),
    )


@router.post("/friends/{username}/request")
def send_request(request: Request, session: SessionDep, me: RequiredUser, username: str, next: Annotated[str, Form()] = ""):
    target = _target(session, me, username)
    if is_blocked(session, me.id, target.id):
        flash(request, "無法送出好友邀請")
        return RedirectResponse("/me/friends", status_code=303)
    f = get_friendship(session, me.id, target.id)
    if f is None:
        session.add(Friendship(requester_id=me.id, addressee_id=target.id))
        flash(request, f"已送出好友邀請給 {target.display_name}")
    elif f.status == FriendStatus.pending and f.addressee_id == me.id:
        # They already asked us: sending back means yes.
        f.status, f.responded_at = FriendStatus.accepted, utcnow()
        session.add(f)
        flash(request, f"你和 {target.display_name} 成為好友了")
    session.commit()
    return _back(next, target)


@router.post("/friends/{username}/accept")
def accept(request: Request, session: SessionDep, me: RequiredUser, username: str, next: Annotated[str, Form()] = ""):
    target = _target(session, me, username)
    f = get_friendship(session, me.id, target.id)
    if f and f.status == FriendStatus.pending and f.addressee_id == me.id:
        f.status, f.responded_at = FriendStatus.accepted, utcnow()
        session.add(f)
        session.commit()
        flash(request, f"你和 {target.display_name} 成為好友了")
    return _back(next, target)


@router.post("/friends/{username}/decline")
def decline(request: Request, session: SessionDep, me: RequiredUser, username: str, next: Annotated[str, Form()] = ""):
    """Decline an incoming request, cancel an outgoing one, or unfriend: all remove the row."""
    target = _target(session, me, username)
    f = get_friendship(session, me.id, target.id)
    if f:
        was_friend = f.status == FriendStatus.accepted
        session.delete(f)
        session.commit()
        if was_friend:
            flash(request, f"已解除與 {target.display_name} 的好友關係")
    return _back(next, target)


@router.post("/friends/{username}/block")
def block(request: Request, session: SessionDep, me: RequiredUser, username: str):
    target = _target(session, me, username)
    if f := get_friendship(session, me.id, target.id):
        session.delete(f)
    exists = session.exec(select(Block).where(Block.blocker_id == me.id, Block.blocked_id == target.id)).first()
    if exists is None:
        session.add(Block(blocker_id=me.id, blocked_id=target.id))
    session.commit()
    flash(request, f"已封鎖 {target.display_name}。你們互相看不到對方的頁面，也不能再送邀請。")
    return RedirectResponse("/me/friends", status_code=303)


@router.post("/friends/{username}/unblock")
def unblock(request: Request, session: SessionDep, me: RequiredUser, username: str):
    target = _target(session, me, username)
    row = session.exec(select(Block).where(Block.blocker_id == me.id, Block.blocked_id == target.id)).first()
    if row:
        session.delete(row)
        session.commit()
        flash(request, f"已解除封鎖 {target.display_name}")
    return RedirectResponse("/me/friends", status_code=303)
