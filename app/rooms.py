"""Live game rooms: a short code to share, a player list, and a JSON state that every player polls.

Clients poll `version()` every couple of seconds and reload when it changes; every write bumps it.
"""

import json
import secrets
from datetime import timedelta, timezone

from sqlmodel import Session, col, select

from app.models import GameRoom, RoomPlayer, User, utcnow

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to misread
CODE_LENGTH = 6
ROOM_TTL = timedelta(hours=24)


def _new_code(session: Session) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if session.exec(select(GameRoom.id).where(GameRoom.code == code)).first() is None:
            return code


def create_room(session: Session, host: User, kind: str, state: dict | None = None) -> GameRoom:
    room = GameRoom(code=_new_code(session), kind=kind, host_id=host.id, state=json.dumps(state or {}))
    session.add(room)
    session.flush()
    session.add(RoomPlayer(room_id=room.id, user_id=host.id, seat=0))
    session.commit()
    session.refresh(room)
    return room


def get_room(session: Session, code: str, kind: str) -> GameRoom | None:
    room = session.exec(select(GameRoom).where(GameRoom.code == code.upper(), GameRoom.kind == kind)).first()
    if room is None:
        return None
    created = room.created_at if room.created_at.tzinfo else room.created_at.replace(tzinfo=timezone.utc)
    return room if utcnow() - created < ROOM_TTL else None


def players(session: Session, room: GameRoom) -> list[User]:
    rows = session.exec(
        select(User).join(RoomPlayer, col(RoomPlayer.user_id) == User.id).where(RoomPlayer.room_id == room.id).order_by(RoomPlayer.seat)
    ).all()
    return list(rows)


def is_player(session: Session, room: GameRoom, user: User) -> bool:
    return session.exec(select(RoomPlayer.id).where(RoomPlayer.room_id == room.id, RoomPlayer.user_id == user.id)).first() is not None


def join(session: Session, room: GameRoom, user: User) -> None:
    seat = len(players(session, room))
    session.add(RoomPlayer(room_id=room.id, user_id=user.id, seat=seat))
    touch(session, room)


def load(room: GameRoom) -> dict:
    return json.loads(room.state or "{}")


def save(session: Session, room: GameRoom, state: dict, status: str | None = None) -> None:
    room.state = json.dumps(state, ensure_ascii=False)
    if status:
        room.status = status
    touch(session, room)


def touch(session: Session, room: GameRoom) -> None:
    room.updated_at = utcnow()
    session.add(room)
    session.commit()


def version(room: GameRoom) -> str:
    return f"{room.status}:{room.updated_at.isoformat()}"
