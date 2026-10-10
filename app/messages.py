"""私訊: one-to-one messages. Allowed between accepted friends, or between someone who posted on
附近朋友 and a person who responded to it. Blocks and locked accounts stop everything."""

from dataclasses import dataclass

from sqlmodel import Session, col, func, or_, select

from app.auth import is_locked
from app.models import CollectionEntry, Message, NearbyPost, NearbyReply, User, Work, utcnow
from app.privacy import can_view, get_privacy
from app.social import are_friends, is_blocked

MAX_MESSAGE = 1000
THREAD_LIMIT = 300  # most recent messages shown in a conversation
OPENERS = 4


def nearby_connected(session: Session, a: int, b: int) -> bool:
    """One of them responded to the other's 附近 post."""
    return session.exec(
        select(NearbyReply.id)
        .join(NearbyPost, col(NearbyPost.id) == NearbyReply.post_id)
        .where(or_(
            (col(NearbyReply.user_id) == a) & (col(NearbyPost.user_id) == b),
            (col(NearbyReply.user_id) == b) & (col(NearbyPost.user_id) == a),
        ))
    ).first() is not None


def can_message(session: Session, me: User, other: User) -> bool:
    if me.id == other.id or is_locked(other) or is_blocked(session, me.id, other.id):
        return False
    return are_friends(session, me.id, other.id) or nearby_connected(session, me.id, other.id)


def send(session: Session, me: User, other: User, body: str) -> Message:
    message = Message(sender_id=me.id, recipient_id=other.id, body=body)
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def thread(session: Session, me: User, other: User, after: int = 0) -> list[Message]:
    pair = or_(
        (col(Message.sender_id) == me.id) & (col(Message.recipient_id) == other.id),
        (col(Message.sender_id) == other.id) & (col(Message.recipient_id) == me.id),
    )
    rows = session.exec(
        select(Message).where(pair, col(Message.id) > after).order_by(col(Message.id).desc()).limit(THREAD_LIMIT)
    ).all()
    return list(reversed(rows))


def mark_read(session: Session, me: User, other: User) -> None:
    unread = session.exec(
        select(Message).where(Message.sender_id == other.id, Message.recipient_id == me.id, col(Message.read_at).is_(None))
    ).all()
    now = utcnow()
    for m in unread:
        m.read_at = now
        session.add(m)
    if unread:
        session.commit()


def unread_count(session: Session, me_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(Message).where(Message.recipient_id == me_id, col(Message.read_at).is_(None))
    ).one()


@dataclass
class Conversation:
    other: User
    last: Message
    unread: int


def conversations(session: Session, me: User) -> list[Conversation]:
    rows = session.exec(
        select(Message)
        .where(or_(Message.sender_id == me.id, Message.recipient_id == me.id))
        .order_by(col(Message.id).desc())
        .limit(3000)
    ).all()
    latest: dict[int, Message] = {}
    unread: dict[int, int] = {}
    for m in rows:
        other_id = m.recipient_id if m.sender_id == me.id else m.sender_id
        latest.setdefault(other_id, m)
        if m.recipient_id == me.id and m.read_at is None:
            unread[other_id] = unread.get(other_id, 0) + 1
    if not latest:
        return []
    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(list(latest))))}
    return [
        Conversation(users[uid], msg, unread.get(uid, 0))
        for uid, msg in latest.items()
        if uid in users and not is_locked(users[uid]) and not is_blocked(session, me.id, uid)
    ]


def shared_works(session: Session, me: User, other: User, limit: int = OPENERS) -> list[Work]:
    """Works both collected, limited to categories `other` lets `me` see."""
    shown = get_privacy(session, other.id)
    friends = are_friends(session, me.id, other.id)

    def collected(user_id: int) -> dict[int, Work]:
        return {
            w.id: w for _, w in session.exec(
                select(CollectionEntry, Work)
                .join(Work, col(Work.id) == CollectionEntry.work_id)
                .where(CollectionEntry.user_id == user_id, col(CollectionEntry.hidden).is_(False),
                       col(CollectionEntry.pending_review).is_(False))
            ).all()
        }

    theirs = {wid for wid, w in collected(other.id).items() if can_view(shown[w.category], other, me, is_friend=friends)}
    return [w for wid, w in collected(me.id).items() if wid in theirs][:limit]


def openers(session: Session, me: User, other: User) -> list[str]:
    """Conversation starters from works you both collected."""
    return [f"你也常聽〈{w.title}〉嗎？" if w.category.value == "music" else f"你也喜歡《{w.title}》嗎？"
            for w in shared_works(session, me, other)]
