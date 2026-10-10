"""作品討論與評分: everyone's verdicts on a work, 短評, the work's 留言區 and the 討論區 notes.

Stats count every confirmed, unhidden entry, including ones in categories their owner keeps private
or friends-only: those count anonymously and never show a name. Reviews and comments are public
posts; a reviewer's own tier/tag is shown next to the review only if the viewer may see it."""

from collections import Counter
from datetime import timedelta
from dataclasses import dataclass, field

from sqlmodel import Session, col, func, select

from app.anime import BOOK_STATUSES, TIERED, TIERS
from app.auth import is_locked
from app.models import (
    Category,
    CollectionEntry,
    Post,
    PostReply,
    Review,
    ReviewLike,
    User,
    Work,
    WorkComment,
    utcnow,
)
from app.privacy import can_view, get_privacy
from app.social import blocked_ids, friend_ids

MAX_REVIEW = 500
MAX_COMMENT = 300
MAX_NOTE = 200
TOP_TAGS = 5
NOTE_COLORS = [("yellow", "黃"), ("pink", "粉"), ("blue", "藍"), ("green", "綠"), ("purple", "紫"), ("orange", "橘")]
NOTE_COLOR_KEYS = {k for k, _ in NOTE_COLORS}
NOTE_DAYS = 7  # notes leave the wall after this; their link keeps working


@dataclass
class Share:
    key: str
    label: str
    count: int
    pct: int


@dataclass
class WorkStats:
    collectors: int = 0
    rated: int = 0
    tiers: list[Share] = field(default_factory=list)
    tags: list[tuple[str, int]] = field(default_factory=list)
    statuses: list[Share] = field(default_factory=list)
    avg_minutes: int | None = None  # games: mean playtime of players who played
    total_plays: int | None = None  # music / Netflix views


def _shares(counts: Counter, keys: list[tuple[str, str]], total: int) -> list[Share]:
    return [Share(k, label, counts[k], round(counts[k] * 100 / total) if total else 0) for k, label in keys]


def work_stats(session: Session, work: Work) -> WorkStats:
    entries = [
        e for e, u in session.exec(
            select(CollectionEntry, User)
            .join(User, col(User.id) == CollectionEntry.user_id)
            .where(
                CollectionEntry.work_id == work.id,
                col(CollectionEntry.pending_review).is_(False),
                col(CollectionEntry.hidden).is_(False),
            )
        ).all()
        if not is_locked(u)
    ]
    stats = WorkStats(collectors=len(entries))
    if work.category in TIERED:
        tiers = Counter(e.tier for e in entries if e.tier)
        stats.rated = sum(tiers.values())
        stats.tiers = _shares(tiers, TIERS, stats.rated)
        stats.tags = Counter(e.tag for e in entries if e.tag).most_common(TOP_TAGS)
    if work.category == Category.book:
        statuses = Counter(e.status for e in entries if e.status)
        stats.statuses = _shares(statuses, BOOK_STATUSES, sum(statuses.values()))
    if work.category == Category.game:
        played = [e.playtime_minutes for e in entries if e.playtime_minutes]
        stats.avg_minutes = round(sum(played) / len(played)) if played else None
    plays = sum(e.play_count or 0 for e in entries)
    stats.total_plays = plays or None
    return stats


def hidden_authors(session: Session, viewer: User | None) -> set[int]:
    """Authors whose posts the viewer shouldn't see: blocked either way, or locked accounts."""
    locked = {u.id for u in session.exec(select(User).where(col(User.birth_date).is_not(None))) if is_locked(u)}
    return locked | (blocked_ids(session, viewer.id) if viewer else set())


@dataclass
class ReviewView:
    review: Review
    author: User
    likes: int
    liked: bool
    entry: CollectionEntry | None  # author's entry, only when the viewer may see that category


def reviews_for(session: Session, work: Work, viewer: User | None, newest: bool = False) -> list[ReviewView]:
    hidden = hidden_authors(session, viewer)
    rows = [
        (r, u) for r, u in session.exec(
            select(Review, User).join(User, col(User.id) == Review.user_id).where(Review.work_id == work.id)
        ).all()
        if u.id not in hidden
    ]
    if not rows:
        return []
    ids = [r.id for r, _ in rows]
    likes = dict(session.exec(
        select(ReviewLike.review_id, func.count()).where(col(ReviewLike.review_id).in_(ids)).group_by(col(ReviewLike.review_id))
    ).all())
    mine = set(session.exec(
        select(ReviewLike.review_id).where(col(ReviewLike.review_id).in_(ids), ReviewLike.user_id == viewer.id)
    ).all()) if viewer else set()
    entries = {
        e.user_id: e for e in session.exec(
            select(CollectionEntry).where(
                CollectionEntry.work_id == work.id,
                col(CollectionEntry.user_id).in_([u.id for _, u in rows]),
                col(CollectionEntry.pending_review).is_(False),
                col(CollectionEntry.hidden).is_(False),
            )
        )
    }
    friends = friend_ids(session, viewer.id) if viewer else set()
    views = []
    for r, u in rows:
        entry = entries.get(u.id)
        if entry and not can_view(get_privacy(session, u.id)[work.category], u, viewer, is_friend=u.id in friends):
            entry = None
        views.append(ReviewView(r, u, likes.get(r.id, 0), r.id in mine, entry))
    if newest:
        views.sort(key=lambda v: v.review.updated_at, reverse=True)
    else:
        views.sort(key=lambda v: (v.likes, v.review.updated_at), reverse=True)
    # The viewer's own review always comes first.
    views.sort(key=lambda v: viewer is None or v.author.id != viewer.id)
    return views


def comments_for(session: Session, work: Work, viewer: User | None) -> list[tuple[WorkComment, User]]:
    hidden = hidden_authors(session, viewer)
    return [
        (c, u) for c, u in session.exec(
            select(WorkComment, User)
            .join(User, col(User.id) == WorkComment.user_id)
            .where(WorkComment.work_id == work.id)
            .order_by(col(WorkComment.created_at).desc())
        ).all()
        if u.id not in hidden
    ]


def community_counts(session: Session, work_id: int) -> tuple[int, int]:
    """(短評, 留言) counts for the link on a personal work page."""
    reviews = session.exec(select(func.count()).select_from(Review).where(Review.work_id == work_id)).one()
    comments = session.exec(select(func.count()).select_from(WorkComment).where(WorkComment.work_id == work_id)).one()
    return reviews, comments


# ---------- 討論區 ----------


def notes(session: Session, viewer: User | None, category: Category | None, limit: int, offset: int = 0) -> list[tuple[Post, User]]:
    hidden = hidden_authors(session, viewer)
    since = utcnow() - timedelta(days=NOTE_DAYS)
    query = select(Post, User).join(User, col(User.id) == Post.user_id).where(col(Post.created_at) >= since)
    if category is not None:
        query = query.where(Post.category == category)
    if hidden:
        query = query.where(col(Post.user_id).not_in(hidden))
    query = query.order_by(col(Post.last_activity_at).desc(), col(Post.id).desc()).offset(offset).limit(limit)
    return list(session.exec(query).all())


def note_expired(post: Post) -> bool:
    """Off the wall (older than NOTE_DAYS); still reachable by its link."""
    created = post.created_at if post.created_at.tzinfo else post.created_at.replace(tzinfo=utcnow().tzinfo)
    return created < utcnow() - timedelta(days=NOTE_DAYS)


def replies_for(session: Session, post: Post, viewer: User | None) -> list[tuple[PostReply, User]]:
    hidden = hidden_authors(session, viewer)
    return [
        (r, u) for r, u in session.exec(
            select(PostReply, User)
            .join(User, col(User.id) == PostReply.user_id)
            .where(PostReply.post_id == post.id)
            .order_by(col(PostReply.created_at))
        ).all()
        if u.id not in hidden
    ]
