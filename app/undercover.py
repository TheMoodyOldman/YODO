"""猜誰是臥底.

Everyone gets the same 4×4 grid. Civilians see word A circled; the undercover sees word B and
doesn't know they're the undercover. Players describe their word in turn, then vote. If the
undercover survives the vote they win; if caught they may guess A: right = tie, wrong = civilians win.
"""

import random
from collections import Counter

from sqlmodel import Session, col, func, select

from app.models import Category, CategoryPrivacy, CollectionEntry, User, Visibility, Work, WorkGenre
from app.services import anilist

MIN_PLAYERS, MAX_PLAYERS = 3, 8
GRID = 16
MAX_DESC = 60
THEMES = {"characters": "動畫角色", "anime": "動畫作品", "game": "遊戲作品"}
RESULTS = {"spy": "臥底獲勝", "civilians": "平民獲勝", "tie": "平手"}


class NotEnough(Exception):
    """Not enough material for a 16-square grid."""


def _shared_works(session: Session, players: list[User], category: Category) -> list[tuple[Work, int]]:
    """Works in players' collections (non-private categories), most shared first."""
    private = set(
        session.exec(
            select(CategoryPrivacy.user_id).where(
                col(CategoryPrivacy.user_id).in_([p.id for p in players]),
                CategoryPrivacy.category == category,
                CategoryPrivacy.visibility == Visibility.private,
            )
        )
    )
    ids = [p.id for p in players if p.id not in private]
    if not ids:
        return []
    rows = session.exec(
        select(Work, func.count(func.distinct(CollectionEntry.user_id)))
        .join(CollectionEntry, col(CollectionEntry.work_id) == Work.id)
        .where(
            col(CollectionEntry.user_id).in_(ids),
            Work.category == category,
            col(CollectionEntry.hidden).is_(False),
            col(CollectionEntry.pending_review).is_(False),
        )
        .group_by(col(Work.id))
    ).all()
    return sorted(rows, key=lambda r: (r[1], r[0].id), reverse=True)


def _popular(session: Session, category: Category, exclude: set[int], limit: int) -> list[Work]:
    rows = session.exec(
        select(Work)
        .join(CollectionEntry, col(CollectionEntry.work_id) == Work.id)
        .where(Work.category == category, col(Work.id).not_in(exclude))
        .group_by(col(Work.id))
        .order_by(func.count(CollectionEntry.id).desc())
        .limit(limit)
    ).all()
    return list(rows)


async def _character_grid(session: Session, players: list[User], rng: random.Random) -> tuple[list[dict], int, int]:
    anime = [w for w, _ in _shared_works(session, players, Category.anime) if w.source == "anilist"][:6]
    casts: list[list[tuple[str, str]]] = []
    for work in anime:
        try:
            cast = await anilist.get_characters(int(work.external_id))
        except Exception:
            cast = []
        if cast:
            casts.append(cast)
        if sum(len(c) for c in casts) >= GRID * 2:
            break
    pairs = [c for c in casts if len(c) >= 2]
    if not pairs or sum(len(c) for c in casts) < GRID:
        raise NotEnough
    # A and B come from the same show, so their descriptions overlap.
    source = pairs[0]
    a_name, b_name = rng.sample(source[:6], 2)
    pool = [c for cast in casts for c in cast if c not in (a_name, b_name)]
    seen, others = set(), []
    for name in pool:
        if name[0] not in seen and name[0] not in (a_name[0], b_name[0]):
            seen.add(name[0])
            others.append(name)
    if len(others) < GRID - 2:
        raise NotEnough
    cells = [a_name, b_name] + rng.sample(others, GRID - 2)
    rng.shuffle(cells)
    grid = [{"t": t, "s": s} for t, s in cells]
    return grid, cells.index(a_name), cells.index(b_name)


def _work_grid(session: Session, players: list[User], category: Category, rng: random.Random) -> tuple[list[dict], int, int]:
    works = [w for w, _ in _shared_works(session, players, category)]
    if len(works) < GRID:
        works += _popular(session, category, {w.id for w in works}, GRID - len(works))
    if len(works) < GRID:
        raise NotEnough
    works = works[: GRID * 2]
    genres: dict[int, set[str]] = {}
    for g in session.exec(select(WorkGenre).where(col(WorkGenre.work_id).in_([w.id for w in works]))):
        genres.setdefault(g.work_id, set()).add(g.genre)
    # Prefer an A/B pair that shares a genre; otherwise any two.
    candidates = [(x, y) for i, x in enumerate(works) for y in works[i + 1:] if genres.get(x.id, set()) & genres.get(y.id, set())]
    a, b = rng.choice(candidates) if candidates else rng.sample(works, 2)
    if rng.random() < 0.5:
        a, b = b, a
    rest = rng.sample([w for w in works if w.id not in (a.id, b.id)], GRID - 2)
    cells = [a, b] + rest
    rng.shuffle(cells)
    grid = [{"t": w.title, "s": w.original_title if w.original_title and w.original_title != w.title else ""} for w in cells]
    return grid, cells.index(a), cells.index(b)


async def deal(session: Session, players: list[User], theme: str, rng: random.Random | None = None) -> dict:
    """Fresh round state. Falls back from characters to anime titles if AniList can't fill a grid."""
    rng = rng or random.Random()
    if theme == "characters":
        try:
            grid, a, b = await _character_grid(session, players, rng)
        except NotEnough:
            theme = "anime"
    if theme != "characters":
        category = Category.game if theme == "game" else Category.anime
        grid, a, b = _work_grid(session, players, category, rng)
    order = [p.id for p in players]
    rng.shuffle(order)
    return {
        "theme": theme, "grid": grid, "a": a, "b": b, "spy": rng.choice(order),
        "order": order, "turn": 0, "descs": {}, "votes": {}, "accused": None, "guess": None, "result": None,
    }


def my_word(state: dict, user_id: int) -> int:
    return state["b"] if state["spy"] == user_id else state["a"]


def describe(state: dict, user_id: int, text: str) -> bool:
    """The current speaker's turn. Returns True when everyone has spoken."""
    if state["order"][state["turn"]] != user_id:
        return False
    state["descs"][str(user_id)] = text.strip()[:MAX_DESC]
    state["turn"] += 1
    return state["turn"] >= len(state["order"])


def vote(state: dict, voter: int, target: int) -> bool:
    """Record a vote; returns True once everyone has voted (then call tally)."""
    if voter == target or target not in state["order"] or voter not in state["order"]:
        return False
    state["votes"][str(voter)] = target
    return len(state["votes"]) == len(state["order"])


def tally(state: dict) -> str:
    """Resolve the vote. Returns the next status: "guess" (undercover caught) or "done"."""
    counts = Counter(state["votes"].values()).most_common()
    top = [uid for uid, n in counts if n == counts[0][1]]
    if len(top) > 1:  # a tied vote eliminates no one: the undercover slips away
        state["accused"], state["result"] = None, "spy"
        return "done"
    state["accused"] = top[0]
    if top[0] != state["spy"]:
        state["result"] = "spy"
        return "done"
    return "guess"


def spy_guess(state: dict, user_id: int, index: int) -> bool:
    if user_id != state["spy"] or state["accused"] != user_id or not 0 <= index < GRID:
        return False
    state["guess"] = index
    state["result"] = "tie" if index == state["a"] else "civilians"
    return True
