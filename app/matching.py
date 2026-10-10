"""同好推薦: rank other users by rare shared tastes, weighted by how invested both people are.

Score = Σ over shared works  idf(work) × √(viewer investment × their investment) × category factor
      + Σ over shared artists (music)  0.5 × idf(artist) × √(...)
      + small bonuses for the same region and overlapping 想找的對象.
Only the candidate's public categories are used, so reasons never reveal anything they keep private.
"""

import math
from dataclasses import dataclass, field

from sqlmodel import Session, col, func, select

from app.anime import TIER_LABELS, TIERED
from app.auth import is_adult
from app.models import (
    Block,
    Category,
    CollectionEntry,
    Friendship,
    MatchDismiss,
    Report,
    User,
    Visibility,
    Work,
)
from app.privacy import get_privacy

REGIONS = [
    "基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "台中市", "彰化縣", "南投縣", "雲林縣",
    "嘉義市", "嘉義縣", "台南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣", "海外",
]
LOOKING_FOR = [
    ("game", "一起玩遊戲"),
    ("anime", "聊動畫"),
    ("music", "交換歌單"),
    ("live", "一起去演唱會、展覽"),
    ("chat", "單純聊天"),
]
LOOKING_LABELS = dict(LOOKING_FOR)
REPORT_THRESHOLD = 3  # distinct unresolved reporters before someone leaves recommendations
MIN_ENTRIES = 3  # the viewer needs some data before recommendations mean anything

CATEGORY_FACTOR = {Category.game: 1.0, Category.anime: 1.2, Category.music: 0.6, Category.film: 1.1, Category.book: 1.2}
ARTIST_FACTOR = 0.5
TIER_WEIGHT = {"must_watch": 3.0, "great": 2.5, "good": 2.0, "okay": 1.2, "bad": 0.6, "dropped": 0.4}
SAME_TIER_BONUS, SAME_TAG_BONUS = 1.3, 1.2
REGION_BONUS, LOOKING_BONUS = 0.5, 0.5
HOUR_MARKS = (1000, 500, 300, 200, 100, 50, 20, 10)


@dataclass
class Reason:
    text: str
    category: Category
    rare: bool
    score: float


@dataclass
class Match:
    user: User
    score: float
    shared: int
    reasons: list[Reason] = field(default_factory=list)
    common_looking: list[str] = field(default_factory=list)
    same_region: bool = False


def looking_keys(user: User) -> list[str]:
    return [k for k in (user.looking_for or "").split(",") if k in LOOKING_LABELS]


def _weight(entry: CollectionEntry, category: Category) -> float:
    if category == Category.game:
        return math.log1p((entry.playtime_minutes or 0) / 60)
    if category == Category.music:
        return math.log1p(entry.play_count or 0)
    return TIER_WEIGHT.get(entry.tier or "", 1.0)


def _eligible_ids(session: Session, viewer: User) -> list[int]:
    """Adults who haven't opted out, aren't already connected to / blocked by / dismissed or
    reported by the viewer, and aren't under review for repeated reports."""
    excluded = {viewer.id}
    for a, b in session.exec(select(Friendship.requester_id, Friendship.addressee_id)):
        if viewer.id in (a, b):
            excluded |= {a, b}
    for a, b in session.exec(select(Block.blocker_id, Block.blocked_id)):
        if viewer.id in (a, b):
            excluded |= {a, b}
    excluded |= set(session.exec(select(MatchDismiss.dismissed_id).where(MatchDismiss.user_id == viewer.id)))
    excluded |= set(session.exec(select(Report.reported_id).where(Report.reporter_id == viewer.id)))
    flagged = set(
        session.exec(
            select(Report.reported_id)
            .where(col(Report.resolved).is_(None))
            .group_by(col(Report.reported_id))
            .having(func.count(func.distinct(Report.reporter_id)) >= REPORT_THRESHOLD)
        )
    )
    users = session.exec(select(User).where(col(User.id).not_in(excluded | flagged))).all()
    return [u.id for u in users if is_adult(u.birth_date) and not u.hide_from_match]


def _entries(session: Session, user_ids: list[int]) -> list[tuple[CollectionEntry, Work]]:
    if not user_ids:
        return []
    return list(
        session.exec(
            select(CollectionEntry, Work)
            .join(Work, col(Work.id) == CollectionEntry.work_id)
            .where(
                col(CollectionEntry.user_id).in_(user_ids),
                col(CollectionEntry.hidden).is_(False),
                col(CollectionEntry.pending_review).is_(False),
            )
        ).all()
    )


def _hours_text(title: str, minutes_a: int, minutes_b: int) -> str:
    both = min(minutes_a, minutes_b) / 60
    mark = next((m for m in HOUR_MARKS if both >= m), None)
    return f"你們都在《{title}》玩了超過 {mark} 小時" if mark else f"你們都玩過《{title}》"


def _reason_text(work: Work, mine: CollectionEntry, theirs: CollectionEntry) -> str:
    if work.category == Category.game:
        return _hours_text(work.title, mine.playtime_minutes or 0, theirs.playtime_minutes or 0)
    if work.category in TIERED:
        if mine.tier and mine.tier == theirs.tier:
            return f"你們都把《{work.title}》評為「{TIER_LABELS[mine.tier]}」"
        if mine.tag and mine.tag == theirs.tag:
            return f"你們都覺得《{work.title}》#{mine.tag}"
        return f"你們都{'讀過' if work.category == Category.book else '看過'}《{work.title}》"
    artist = f" — {work.creator}" if work.creator else ""
    if min(mine.play_count or 0, theirs.play_count or 0) >= 5:
        return f"你們都常聽〈{work.title}〉{artist}"
    return f"你們都聽過〈{work.title}〉{artist}"


def empty_reason(session: Session, viewer: User) -> str:
    """Why find_matches came back empty: "few_entries", "no_people" or "no_overlap"."""
    if len(_entries(session, [viewer.id])) < MIN_ENTRIES:
        return "few_entries"
    return "no_overlap" if _eligible_ids(session, viewer) else "no_people"


def find_matches(session: Session, viewer: User, limit: int = 20) -> list[Match]:
    mine = {w.id: (e, w) for e, w in _entries(session, [viewer.id])}
    if len(mine) < MIN_ENTRIES:
        return []
    candidates = _eligible_ids(session, viewer)
    if not candidates:
        return []

    # Candidates contribute only the categories they show to everyone.
    public = {uid: {c for c, v in get_privacy(session, uid).items() if v == Visibility.public} for uid in candidates}
    theirs: dict[int, dict[int, CollectionEntry]] = {uid: {} for uid in candidates}
    their_artists: dict[int, dict[str, int]] = {uid: {} for uid in candidates}
    for e, w in _entries(session, candidates):
        if w.category not in public[e.user_id]:
            continue
        theirs[e.user_id][w.id] = e
        if w.category == Category.music and w.creator:
            artists = their_artists[e.user_id]
            artists[w.creator.casefold()] = artists.get(w.creator.casefold(), 0) + (e.play_count or 0)

    # Popularity across everyone (not just candidates) for rarity weighting.
    population = max(session.exec(select(func.count()).select_from(User)).one(), 1)
    work_df = dict(
        session.exec(
            select(CollectionEntry.work_id, func.count(func.distinct(CollectionEntry.user_id)))
            .where(col(CollectionEntry.work_id).in_(list(mine)))
            .group_by(col(CollectionEntry.work_id))
        ).all()
    )
    my_artists: dict[str, tuple[str, int]] = {}
    for e, w in mine.values():
        if w.category == Category.music and w.creator:
            name, plays = my_artists.get(w.creator.casefold(), (w.creator, 0))
            my_artists[w.creator.casefold()] = (name, plays + (e.play_count or 0))
    artist_df: dict[str, int] = {}
    if my_artists:
        for uid, creator in set(
            session.exec(
                select(CollectionEntry.user_id, Work.creator)
                .join(Work, col(Work.id) == CollectionEntry.work_id)
                .where(Work.category == Category.music, col(Work.creator).is_not(None))
            ).all()
        ):
            key = creator.casefold()
            if key in my_artists:
                artist_df[key] = artist_df.get(key, 0) + 1

    def idf(df: int) -> float:
        return math.log((population + 1) / max(df, 1))

    def rare(df: int) -> bool:
        return df <= max(2, math.ceil(population * 0.05))

    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(candidates)))}
    my_looking, matches = set(looking_keys(viewer)), []
    for uid in candidates:
        reasons: list[Reason] = []
        for work_id in mine.keys() & theirs[uid].keys():
            my_entry, work = mine[work_id]
            their_entry = theirs[uid][work_id]
            df = work_df.get(work_id, 1)
            score = idf(df) * math.sqrt(_weight(my_entry, work.category) * _weight(their_entry, work.category))
            score *= CATEGORY_FACTOR[work.category]
            if work.category in TIERED:
                if my_entry.tier and my_entry.tier == their_entry.tier:
                    score *= SAME_TIER_BONUS
                if my_entry.tag and my_entry.tag == their_entry.tag:
                    score *= SAME_TAG_BONUS
            reasons.append(Reason(_reason_text(work, my_entry, their_entry), work.category, rare(df), score))
        for key in my_artists.keys() & their_artists[uid].keys():
            name, my_plays = my_artists[key]
            df = artist_df.get(key, 1)
            score = ARTIST_FACTOR * idf(df) * math.sqrt(math.log1p(my_plays) * math.log1p(their_artists[uid][key]))
            reasons.append(Reason(f"你們都愛聽 {name}", Category.music, rare(df), score))
        if not reasons:
            continue  # region / 想找的對象 alone isn't a shared interest

        user = users[uid]
        common = [LOOKING_LABELS[k] for k in looking_keys(user) if k in my_looking]
        same_region = bool(viewer.region and viewer.region == user.region)
        reasons.sort(key=lambda r: r.score, reverse=True)
        total = sum(r.score for r in reasons) + REGION_BONUS * same_region + LOOKING_BONUS * len(common)
        matches.append(Match(user, total, len(reasons), reasons[:3], common, same_region))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
