"""Friendships (mutual, request/accept) and blocks."""

from enum import StrEnum

from sqlmodel import Session, col, func, or_, select

from app.models import Block, FriendStatus, Friendship, User


class Relation(StrEnum):
    self = "self"
    none = "none"
    outgoing = "outgoing"  # viewer asked, waiting for owner
    incoming = "incoming"  # owner asked the viewer
    friends = "friends"
    blocked = "blocked"  # either side blocked the other


def get_friendship(session: Session, a_id: int, b_id: int) -> Friendship | None:
    return session.exec(
        select(Friendship).where(
            or_(
                (col(Friendship.requester_id) == a_id) & (col(Friendship.addressee_id) == b_id),
                (col(Friendship.requester_id) == b_id) & (col(Friendship.addressee_id) == a_id),
            )
        )
    ).first()


def is_blocked(session: Session, a_id: int, b_id: int) -> bool:
    """True if either user blocked the other."""
    return (
        session.exec(
            select(Block.id).where(
                or_(
                    (col(Block.blocker_id) == a_id) & (col(Block.blocked_id) == b_id),
                    (col(Block.blocker_id) == b_id) & (col(Block.blocked_id) == a_id),
                )
            )
        ).first()
        is not None
    )


def are_friends(session: Session, a_id: int, b_id: int) -> bool:
    f = get_friendship(session, a_id, b_id)
    return f is not None and f.status == FriendStatus.accepted


def friend_ids(session: Session, user_id: int) -> set[int]:
    rows = session.exec(
        select(Friendship.requester_id, Friendship.addressee_id).where(
            Friendship.status == FriendStatus.accepted,
            or_(col(Friendship.requester_id) == user_id, col(Friendship.addressee_id) == user_id),
        )
    ).all()
    return {b if a == user_id else a for a, b in rows}


def relation(session: Session, viewer: User | None, owner: User) -> Relation | None:
    """How the viewer relates to the owner; None for logged-out visitors."""
    if viewer is None:
        return None
    if viewer.id == owner.id:
        return Relation.self
    if is_blocked(session, viewer.id, owner.id):
        return Relation.blocked
    f = get_friendship(session, viewer.id, owner.id)
    if f is None:
        return Relation.none
    if f.status == FriendStatus.accepted:
        return Relation.friends
    return Relation.outgoing if f.requester_id == viewer.id else Relation.incoming


def incoming_request_count(session: Session, user_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(Friendship).where(
            Friendship.addressee_id == user_id, Friendship.status == FriendStatus.pending
        )
    ).one()


def blocked_ids(session: Session, user_id: int) -> set[int]:
    """Everyone this user blocked or was blocked by: their posts are hidden both ways."""
    rows = session.exec(
        select(Block.blocker_id, Block.blocked_id).where(
            or_(col(Block.blocker_id) == user_id, col(Block.blocked_id) == user_id)
        )
    ).all()
    return {b if a == user_id else a for a, b in rows}
