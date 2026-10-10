"""Inviting friends straight into a live game room (no link to copy). The invitee sees a pop-up
on whatever page they're on (static/js/invites.js polls /games/invites)."""

from datetime import timedelta

from sqlmodel import Session, col, select

from app import rooms, undercover
from app.auth import is_locked
from app.models import GameInvite, GameRoom, User, utcnow
from app.social import blocked_ids, friend_ids

INVITE_MINUTES = 30
KINDS = {"song": "猜歌對戰", "undercover": "猜誰是臥底"}
CAPACITY = {"song": 2, "undercover": undercover.MAX_PLAYERS}


def _fresh(when) -> bool:
    when = when if when.tzinfo else when.replace(tzinfo=utcnow().tzinfo)
    return utcnow() - when < timedelta(minutes=INVITE_MINUTES)


def invitable(session: Session, room: GameRoom, me: User) -> list[tuple[User, bool]]:
    """Friends who could join, with whether they've already been invited to this room."""
    in_room = {p.id for p in rooms.players(session, room)}
    ids = friend_ids(session, me.id) - in_room - blocked_ids(session, me.id)
    if not ids:
        return []
    invited = {
        i.to_id for i in session.exec(select(GameInvite).where(GameInvite.room_id == room.id, col(GameInvite.declined).is_(False)))
        if _fresh(i.created_at)
    }
    friends = [u for u in session.exec(select(User).where(col(User.id).in_(ids))) if not is_locked(u)]
    return [(u, u.id in invited) for u in sorted(friends, key=lambda u: u.display_name.casefold())]


def send(session: Session, room: GameRoom, me: User, friend: User) -> str | None:
    """Invite a friend; returns an error message or None."""
    if room.status != "lobby":
        return "遊戲已經開始了"
    if not rooms.is_player(session, room, me):
        return "你不在這個房間"
    if friend.id not in {u.id for u, _ in invitable(session, room, me)}:
        return "只能邀請還不在房間裡的好友"
    if len(rooms.players(session, room)) >= CAPACITY[room.kind]:
        return "房間已滿"
    invite = session.exec(select(GameInvite).where(GameInvite.room_id == room.id, GameInvite.to_id == friend.id)).first()
    if invite is None:
        invite = GameInvite(room_id=room.id, from_id=me.id, to_id=friend.id)
    invite.from_id, invite.created_at, invite.declined = me.id, utcnow(), False
    session.add(invite)
    session.commit()
    return None


def pending(session: Session, me: User) -> list[dict]:
    """Invites I can still act on: recent, not declined, the room still waiting and not full."""
    hidden = blocked_ids(session, me.id)
    out = []
    for invite, room, sender in session.exec(
        select(GameInvite, GameRoom, User)
        .join(GameRoom, col(GameRoom.id) == GameInvite.room_id)
        .join(User, col(User.id) == GameInvite.from_id)
        .where(GameInvite.to_id == me.id, col(GameInvite.declined).is_(False), GameRoom.status == "lobby")
        .order_by(col(GameInvite.created_at).desc())
    ).all():
        if not _fresh(invite.created_at) or sender.id in hidden or room.kind not in KINDS:
            continue
        people = rooms.players(session, room)
        if any(p.id == me.id for p in people) or len(people) >= CAPACITY[room.kind]:
            continue
        out.append({"id": invite.id, "from": sender.display_name, "game": KINDS[room.kind],
                    "url": f"/games/{room.kind}/{room.code}", "avatar": sender.avatar_photo_id})
    return out


def decline(session: Session, me: User, invite_id: int) -> bool:
    invite = session.get(GameInvite, invite_id)
    if invite is None or invite.to_id != me.id:
        return False
    invite.declined = True
    session.add(invite)
    session.commit()
    return True
