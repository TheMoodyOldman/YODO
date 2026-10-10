"""小遊戲: 品味契合度挑戰, 猜猜這是誰的收藏, 興趣賓果.

Every game only reads what the viewer is allowed to see of other people (category privacy,
hidden and pending entries excluded), the same rules as profiles.
"""

import math
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, col, func, select

from app.auth import is_locked
from app.importers.youtube import TAIPEI
from app.matching import _weight
from app.models import (
    BingoMark,
    CardEvent,
    Category,
    CollectionEntry,
    MonthlyPlays,
    User,
    Work,
)
from app.privacy import can_view, get_privacy
from app.social import friend_ids

Row = tuple[CollectionEntry, Work]


# ---------- shared helpers ----------

def visible_rows(session: Session, owner: User, viewer: User, is_friend: bool) -> list[Row]:
    privacy = get_privacy(session, owner.id)
    allowed = {c for c in Category if can_view(privacy[c], owner, viewer, is_friend)}
    rows = session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(
            CollectionEntry.user_id == owner.id,
            col(CollectionEntry.hidden).is_(False),
            col(CollectionEntry.pending_review).is_(False),
        )
    ).all()
    return [(e, w) for e, w in rows if w.category in allowed]


def _idf_table(session: Session, work_ids: set[int]) -> tuple[dict[int, float], int]:
    population = max(session.exec(select(func.count()).select_from(User)).one(), 1)
    if not work_ids:
        return {}, population
    df = dict(
        session.exec(
            select(CollectionEntry.work_id, func.count(func.distinct(CollectionEntry.user_id)))
            .where(col(CollectionEntry.work_id).in_(list(work_ids)))
            .group_by(col(CollectionEntry.work_id))
        ).all()
    )
    return {w: math.log((population + 1) / max(df.get(w, 1), 1)) for w in work_ids}, population


def _signature(rows: list[Row], idf: dict[int, float]) -> list[tuple[float, Row]]:
    """Items that best characterise someone: invested in, and not everyone has them."""
    by_cat_max: dict[Category, float] = {}
    for e, w in rows:
        by_cat_max[w.category] = max(by_cat_max.get(w.category, 0), _weight(e, w.category))
    scored = []
    for e, w in rows:
        norm = _weight(e, w.category) / (by_cat_max[w.category] or 1)
        scored.append((norm * (0.5 + idf.get(w.id, 0)), (e, w)))
    return sorted(scored, key=lambda s: s[0], reverse=True)


# ---------- 品味契合度挑戰 ----------

COMPAT_LABELS = [(85, "靈魂伴侶"), (65, "品味相近"), (40, "有共同話題"), (20, "各有所好"), (0, "平行宇宙")]


@dataclass
class Compat:
    pct: int
    label: str
    common_categories: list[Category]
    shared: list[tuple[Work, CollectionEntry, CollectionEntry]] = field(default_factory=list)
    their_picks: list[Row] = field(default_factory=list)  # their favourites the viewer doesn't have
    my_picks: list[Row] = field(default_factory=list)
    per_category: dict[Category, int] = field(default_factory=dict)


def _cosine(a: dict, b: dict) -> float:
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def compatibility(session: Session, viewer: User, other: User, is_friend: bool) -> Compat:
    mine = visible_rows(session, viewer, viewer, True)
    theirs = visible_rows(session, other, viewer, is_friend)
    idf, _ = _idf_table(session, {w.id for _, w in mine} | {w.id for _, w in theirs})

    def vectors(rows: list[Row]) -> tuple[dict[Category, dict[int, float]], dict[str, float]]:
        maxes: dict[Category, float] = {}
        for e, w in rows:
            maxes[w.category] = max(maxes.get(w.category, 0), _weight(e, w.category))
        vecs: dict[Category, dict[int, float]] = {}
        artists: Counter[str] = Counter()
        for e, w in rows:
            weight = _weight(e, w.category) / (maxes[w.category] or 1)
            vecs.setdefault(w.category, {})[w.id] = idf.get(w.id, 0.1) * (0.3 + weight)
            if w.category == Category.music and w.creator:
                artists[w.creator.casefold()] += e.play_count or 0
        return vecs, {k: math.log1p(v) for k, v in artists.items()}

    my_vecs, my_artists = vectors(mine)
    their_vecs, their_artists = vectors(theirs)
    common = [c for c in Category if c in my_vecs and c in their_vecs]
    per_category = {}
    for c in common:
        cos = _cosine(my_vecs[c], their_vecs[c])
        if c == Category.music:
            cos = max(cos, 0.8 * _cosine(my_artists, their_artists))
        per_category[c] = round(100 * math.sqrt(cos))
    pct = round(sum(per_category.values()) / len(per_category)) if per_category else 0
    label = next(text for floor, text in COMPAT_LABELS if pct >= floor)

    mine_by_work = {w.id: (e, w) for e, w in mine}
    theirs_by_work = {w.id: (e, w) for e, w in theirs}
    shared = sorted(
        (
            (mine_by_work[wid][1], mine_by_work[wid][0], theirs_by_work[wid][0])
            for wid in mine_by_work.keys() & theirs_by_work.keys()
        ),
        key=lambda t: idf.get(t[0].id, 0) * math.sqrt(_weight(t[1], t[0].category) * _weight(t[2], t[0].category) + 1e-9),
        reverse=True,
    )
    their_picks = [r for _, r in _signature(theirs, idf) if r[1].id not in mine_by_work and r[1].category in my_vecs][:3]
    my_picks = [r for _, r in _signature(mine, idf) if r[1].id not in theirs_by_work and r[1].category in their_vecs][:3]
    return Compat(pct, label, common, shared[:6], their_picks, my_picks, per_category)


# ---------- 猜猜這是誰的收藏 ----------

GUESS_ROUNDS = 5
GUESS_ITEMS = 3
GUESS_MIN_ITEMS = 3


def guess_candidates(session: Session, viewer: User) -> dict[int, list[Row]]:
    """Friends with enough visible items to make a fair question."""
    out = {}
    for fid in friend_ids(session, viewer.id):
        friend = session.get(User, fid)
        if friend is None or is_locked(friend):
            continue
        rows = visible_rows(session, friend, viewer, True)
        if len(rows) >= GUESS_MIN_ITEMS:
            out[fid] = rows
    return out


def new_guess_game(session: Session, viewer: User, rng: random.Random | None = None) -> list[dict] | None:
    """Rounds as plain dicts (kept in the session cookie): answer id, 3 work ids, option ids."""
    rng = rng or random.Random()
    candidates = guess_candidates(session, viewer)
    if len(candidates) < 2:
        return None
    idf, _ = _idf_table(session, {w.id for rows in candidates.values() for _, w in rows})
    people = list(candidates)
    order = [people[i % len(people)] for i in range(GUESS_ROUNDS)]
    rng.shuffle(order)
    rounds = []
    for answer in order:
        top = [r for _, r in _signature(candidates[answer], idf)][:10]
        picks = rng.sample(top, min(GUESS_ITEMS, len(top)))
        others = rng.sample([p for p in people if p != answer], min(3, len(people) - 1))
        options = others + [answer]
        rng.shuffle(options)
        rounds.append({"a": answer, "w": [w.id for _, w in picks], "o": options})
    return rounds


GUESS_LABELS = [(5, "好友雷達滿分"), (4, "品味偵探"), (3, "還算了解"), (1, "多聊聊吧"), (0, "重新認識一下")]


def guess_label(score: int) -> str:
    return next(text for floor, text in GUESS_LABELS if score >= floor)


# ---------- 興趣賓果 ----------

@dataclass
class BingoStats:
    max_game_minutes: int = 0
    total_game_minutes: int = 0
    games: int = 0
    anime: int = 0
    anime_tiers: set[str] = field(default_factory=set)
    anime_tags: set[str] = field(default_factory=set)
    max_song_plays: int = 0
    top_artist_plays: int = 0
    month_plays: int = 0
    categories: int = 0
    friends: int = 0
    shared_recap: bool = False


def bingo_stats(session: Session, user: User) -> BingoStats:
    st = BingoStats()
    rows = session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, col(CollectionEntry.pending_review).is_(False))
    ).all()
    artists: Counter[str] = Counter()
    cats = set()
    for e, w in rows:
        cats.add(w.category)
        if w.category == Category.game:
            st.games += 1
            st.total_game_minutes += e.playtime_minutes or 0
            st.max_game_minutes = max(st.max_game_minutes, e.playtime_minutes or 0)
        elif w.category == Category.anime:
            st.anime += 1
            if e.tier:
                st.anime_tiers.add(e.tier)
            if e.tag:
                st.anime_tags.add(e.tag)
        else:
            st.max_song_plays = max(st.max_song_plays, e.play_count or 0)
            if w.creator:
                artists[w.creator.casefold()] += e.play_count or 0
    st.top_artist_plays = max(artists.values(), default=0)
    st.categories = len(cats)
    month = datetime.now(TAIPEI).strftime("%Y-%m")
    st.month_plays = session.exec(
        select(func.coalesce(func.sum(MonthlyPlays.plays), 0)).where(MonthlyPlays.user_id == user.id, MonthlyPlays.month == month)
    ).one()
    st.friends = len(friend_ids(session, user.id))
    st.shared_recap = session.exec(
        select(CardEvent.id).where(CardEvent.user_id == user.id, CardEvent.action == "share")
    ).first() is not None
    return st


@dataclass(frozen=True)
class Prompt:
    key: str
    text: str
    auto: Callable[[BingoStats], bool] | None = None  # None: the user ticks it


PROMPTS = [
    # Checked automatically from collection data
    Prompt("game_100h", "有一款遊戲玩超過 100 小時", lambda s: s.max_game_minutes >= 100 * 60),
    Prompt("steam_1000h", "遊戲總時數破 1000 小時", lambda s: s.total_game_minutes >= 1000 * 60),
    Prompt("games_30", "收藏超過 30 款遊戲", lambda s: s.games >= 30),
    Prompt("anime_must", "把一部動畫評為「此生必看」", lambda s: "must_watch" in s.anime_tiers),
    Prompt("anime_bad", "把一部動畫評為「雷」", lambda s: "bad" in s.anime_tiers),
    Prompt("anime_dropped", "棄坑過一部動畫", lambda s: "dropped" in s.anime_tiers),
    Prompt("tag_stomach", "有一部動畫讓你 #胃痛", lambda s: "胃痛" in s.anime_tags),
    Prompt("tag_what", "看完一部動畫只想說 #我看了什麼", lambda s: "我看了什麼" in s.anime_tags),
    Prompt("anime_20", "收藏超過 20 部動畫", lambda s: s.anime >= 20),
    Prompt("song_50", "同一首歌聽超過 50 次", lambda s: s.max_song_plays >= 50),
    Prompt("artist_200", "最愛的歌手播放破 200 次", lambda s: s.top_artist_plays >= 200),
    Prompt("month_300", "這個月聽歌超過 300 次", lambda s: s.month_plays >= 300),
    Prompt("all_three", "遊戲、動畫、音樂都有收藏", lambda s: s.categories >= 3),
    Prompt("friends_3", "有 3 位以上好友", lambda s: s.friends >= 3),
    Prompt("shared_recap", "分享過自己的 Recap", lambda s: s.shared_recap),
    # Ticked by the user
    Prompt("allnighter", "通宵追番"),
    Prompt("gacha", "為了角色課金"),
    Prompt("merch", "買過限定版或周邊"),
    Prompt("concert", "去過演唱會"),
    Prompt("expo", "去過漫展或動漫展"),
    Prompt("dawn", "玩遊戲玩到天亮"),
    Prompt("pilgrimage", "去過動畫聖地巡禮"),
    Prompt("recruit", "成功推坑過朋友"),
    Prompt("rewatch", "同一部作品重看超過 3 次"),
    Prompt("hardware", "為了遊戲買新主機或顯卡"),
    Prompt("source", "看完動畫立刻補原作"),
    Prompt("loop", "單曲循環一整天"),
    Prompt("ktv", "在 KTV 唱動畫歌"),
    Prompt("cosplay", "Cosplay 過"),
    Prompt("launch_day", "排隊買過首發"),
    Prompt("idle", "一邊工作一邊掛遊戲"),
    Prompt("ost", "因為 OST 入坑一部作品"),
    Prompt("cried", "看動畫哭到停不下來"),
    Prompt("ranked", "熬夜打排位"),
    Prompt("vinyl", "收藏過實體專輯或黑膠"),
]
PROMPT_BY_KEY = {p.key: p for p in PROMPTS}
FREE = "free"
BINGO_AUTO = 10  # auto squares per board; the rest are manual
SIZE = 5


def current_month() -> str:
    return datetime.now(TAIPEI).strftime("%Y-%m")


def bingo_board(user: User, month: str) -> list[str]:
    """25 keys, FREE in the middle. Stable for a user within a month, different next month."""
    rng = random.Random(f"{user.id}-{month}")
    autos = [p.key for p in PROMPTS if p.auto]
    manuals = [p.key for p in PROMPTS if not p.auto]
    keys = rng.sample(autos, BINGO_AUTO) + rng.sample(manuals, SIZE * SIZE - 1 - BINGO_AUTO)
    rng.shuffle(keys)
    keys.insert(SIZE * SIZE // 2, FREE)
    return keys


def bingo_marked(session: Session, user: User, month: str, board: list[str]) -> list[bool]:
    stats = bingo_stats(session, user)
    manual = set(session.exec(select(BingoMark.key).where(BingoMark.user_id == user.id, BingoMark.month == month)))
    out = []
    for key in board:
        if key == FREE:
            out.append(True)
        elif (p := PROMPT_BY_KEY[key]).auto:
            out.append(p.auto(stats))
        else:
            out.append(key in manual)
    return out


def bingo_lines(marked: list[bool]) -> int:
    lines = [[r * SIZE + c for c in range(SIZE)] for r in range(SIZE)]
    lines += [[r * SIZE + c for r in range(SIZE)] for c in range(SIZE)]
    lines += [[i * SIZE + i for i in range(SIZE)], [i * SIZE + SIZE - 1 - i for i in range(SIZE)]]
    return sum(all(marked[i] for i in line) for line in lines)
