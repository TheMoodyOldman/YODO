"""附近朋友: say hi to people nearby. Only coarse locations are used: every coordinate is rounded
to a ~1 km grid before it is stored (posts) or kept in the session (the viewer), and other people
only ever see a distance bucket such as "3 公里內". Posts disappear after POST_HOURS.

Flow (privacy first): you post a short message; people near you see your name, interests and
message; you only learn who they are if they respond, and responding opens a 私訊 conversation."""

import math
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import Session, col, select

from app.auth import is_locked
from app.models import NearbyPost, NearbyReply, User, utcnow
from app.social import blocked_ids

GRID = 0.01  # degrees: ~1.1 km north-south, ~1 km east-west in Taiwan
RADII = [1, 3, 5, 10]  # km a post reaches
DEFAULT_RADIUS = 3
POST_HOURS = 24
MAX_BODY = 200
MAX_REPLY = 200
LIST_LIMIT = 50

# Rough centers (city halls) for people who'd rather pick a region than share their position.
REGION_CENTERS = {
    "基隆市": (25.13, 121.74), "台北市": (25.04, 121.56), "新北市": (25.01, 121.47), "桃園市": (24.99, 121.30),
    "新竹市": (24.81, 120.97), "新竹縣": (24.83, 121.01), "苗栗縣": (24.56, 120.82), "台中市": (24.16, 120.65),
    "彰化縣": (24.08, 120.54), "南投縣": (23.90, 120.69), "雲林縣": (23.70, 120.53), "嘉義市": (23.48, 120.45),
    "嘉義縣": (23.46, 120.26), "台南市": (22.99, 120.18), "高雄市": (22.62, 120.31), "屏東縣": (22.68, 120.49),
    "宜蘭縣": (24.73, 121.76), "花蓮縣": (23.99, 121.60), "台東縣": (22.76, 121.14), "澎湖縣": (23.57, 119.58),
    "金門縣": (24.44, 118.32), "連江縣": (26.16, 119.95),
}


def coarse(lat: float, lon: float) -> tuple[float, float] | None:
    """Snap to the grid; None for impossible coordinates."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or math.isnan(lat) or math.isnan(lon):
        return None
    return round(round(lat / GRID) * GRID, 2), round(round(lon / GRID) * GRID, 2)


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def bucket(km: float) -> int:
    """Shown distance: the smallest radius step that covers it (grid error is about 1 km anyway)."""
    return next((r for r in RADII if km <= r), RADII[-1])


def _active(query):
    return query.where(col(NearbyPost.cancelled).is_(False), col(NearbyPost.expires_at) > utcnow())


def hours_left(post: NearbyPost) -> int:
    expires = post.expires_at if post.expires_at.tzinfo else post.expires_at.replace(tzinfo=utcnow().tzinfo)
    return max(1, math.ceil((expires - utcnow()).total_seconds() / 3600))


def my_post(session: Session, user: User) -> NearbyPost | None:
    return session.exec(_active(select(NearbyPost).where(NearbyPost.user_id == user.id))).first()


def publish(session: Session, user: User, where: tuple[float, float], radius: int, body: str) -> NearbyPost:
    """One live post per person: a new one replaces the old."""
    for old in session.exec(_active(select(NearbyPost).where(NearbyPost.user_id == user.id))).all():
        old.cancelled = True
        session.add(old)
    post = NearbyPost(user_id=user.id, lat=where[0], lon=where[1], radius_km=radius, body=body,
                      expires_at=utcnow() + timedelta(hours=POST_HOURS))
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


@dataclass
class NearbyItem:
    post: NearbyPost
    author: User
    km: int
    replied: bool
    shared: list[str] = field(default_factory=list)


def around(session: Session, viewer: User, where: tuple[float, float]) -> list[NearbyItem]:
    """Live posts by others whose reach covers the viewer, nearest first."""
    hidden = blocked_ids(session, viewer.id)
    rows = session.exec(
        _active(select(NearbyPost, User).join(User, col(User.id) == NearbyPost.user_id))
        .where(NearbyPost.user_id != viewer.id)
        .order_by(col(NearbyPost.created_at).desc())
        .limit(500)
    ).all()
    replied = set(session.exec(select(NearbyReply.post_id).where(NearbyReply.user_id == viewer.id)).all())
    items = []
    for post, author in rows:
        if author.id in hidden or is_locked(author):
            continue
        km = distance_km(where, (post.lat, post.lon))
        if km <= post.radius_km:
            items.append(NearbyItem(post, author, bucket(km), post.id in replied))
    items.sort(key=lambda i: (i.km, -i.post.created_at.timestamp()))
    return items[:LIST_LIMIT]


def responders(session: Session, post: NearbyPost, viewer: User) -> list[tuple[NearbyReply, User]]:
    hidden = blocked_ids(session, viewer.id)
    return [
        (r, u) for r, u in session.exec(
            select(NearbyReply, User).join(User, col(User.id) == NearbyReply.user_id)
            .where(NearbyReply.post_id == post.id).order_by(col(NearbyReply.created_at).desc())
        ).all()
        if u.id not in hidden and not is_locked(u)
    ]
