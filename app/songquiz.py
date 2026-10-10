"""猜歌: a live 1-on-1 quiz. Five songs, each revealed in growing clips (3/5/10/25/30 s, Apple
previews); earlier correct guesses score more. Songs come from what both players share first;
when that runs out, songs whose style is close to the other player's taste, popular songs, and
finally songs only one of them has heard (the reveal says whose library it came from).
"""

import random
from urllib.parse import quote

from sqlmodel import Session, col, func, select

from app.games import visible_rows
from app.genres import user_style
from app.models import Category, CollectionEntry, User, Work, WorkGenre, utcnow
from app.services import itunes

ROUNDS = 5
STAGES = [3, 5, 10, 25, 30]  # seconds; the last is the whole preview
POINTS = [5, 4, 3, 2, 1]
OPTIONS = 16
MAX_LOOKUPS = 12  # Apple allows ~20 searches a minute (up to 3 stores each); results are cached on the work


class NotEnoughSongs(Exception):
    pass


def _key(work: Work) -> tuple[str, str]:
    return ((work.creator or "").casefold().strip(), work.title.casefold().strip())


def _music(session: Session, owner: User, viewer: User, is_friend: bool) -> dict[tuple[str, str], tuple[CollectionEntry, Work]]:
    out = {}
    for e, w in visible_rows(session, owner, viewer, is_friend):
        if w.category != Category.music:
            continue
        k = _key(w)
        # Prefer the YouTube copy of a song: it can be embedded after the reveal.
        if k not in out or (w.source == "youtube" and out[k][1].source != "youtube"):
            out[k] = (e, w)
    return out


TIER_LABELS = ["你們都聽過", "你們都喜歡的歌手", "你們都愛的風格", "風格相近", "熱門歌曲", "只有一人聽過"]


def candidate_tiers(session: Session, p1: User, p2: User, is_friend: bool) -> list[list[Work]]:
    """Songs best first: shared songs, songs by shared artists, songs in both players' top styles,
    songs whose style overlaps the other player's taste, the platform's most-collected songs, and
    last any song from either library (so a game can always be made if previews exist)."""
    m1, m2 = _music(session, p1, p2, is_friend), _music(session, p2, p1, is_friend)

    def plays(k) -> int:
        return sum(m[k][0].play_count or 0 for m in (m1, m2) if k in m)

    def best_copy(k) -> Work:
        copies = [m[k][1] for m in (m1, m2) if k in m]
        return next((w for w in copies if w.source == "youtube"), copies[0])

    shared = sorted(m1.keys() & m2.keys(), key=plays, reverse=True)
    tier1 = [best_copy(k) for k in shared]
    artists = {a for a, _ in m1} & {a for a, _ in m2} - {""}
    either = {**m1, **m2}
    tier2 = [best_copy(k) for k in sorted(either, key=plays, reverse=True) if k[0] in artists and k not in shared]

    styles1 = user_style(session, p1, {Category.music}).get(Category.music)
    styles2 = user_style(session, p2, {Category.music}).get(Category.music)
    common_styles = ({g.genre for g in styles1.genres[:5]} if styles1 else set()) & ({g.genre for g in styles2.genres[:5]} if styles2 else set())
    used = {w.id for w in tier1 + tier2}
    tier3 = []
    if common_styles:
        styled = set(session.exec(select(WorkGenre.work_id).where(col(WorkGenre.genre).in_(common_styles))))
        tier3 = [w for k, (e, w) in either.items() if w.id in styled and w.id not in used]
        used |= {w.id for w in tier3}

    # Style overlap: a song from one library scores by how much its genres weigh in the other's taste.
    weights = {
        1: {g.genre: g.pct for g in styles2.genres} if styles2 else {},  # songs from p1, judged by p2's taste
        2: {g.genre: g.pct for g in styles1.genres} if styles1 else {},
    }
    rest = {k: v for k, v in either.items() if v[1].id not in used}
    genres_of: dict[int, set[str]] = {}
    if rest:
        for wid, genre in session.exec(
            select(WorkGenre.work_id, WorkGenre.genre).where(col(WorkGenre.work_id).in_([w.id for _, w in rest.values()]))
        ):
            genres_of.setdefault(wid, set()).add(genre)

    def closeness(k) -> int:
        owner = 1 if k in m1 else 2
        return sum(weights[owner].get(g, 0) for g in genres_of.get(either[k][1].id, ()))

    close = sorted((k for k in rest if closeness(k) > 0), key=lambda k: (closeness(k), plays(k)), reverse=True)
    tier4 = [best_copy(k) for k in close]
    used |= {w.id for w in tier4}
    tier5 = list(
        session.exec(
            select(Work)
            .join(CollectionEntry, col(CollectionEntry.work_id) == Work.id)
            .where(Work.category == Category.music, col(Work.id).not_in(used or {-1}))
            .group_by(col(Work.id))
            .having(func.count(func.distinct(CollectionEntry.user_id)) >= 2)
            .order_by(func.count(func.distinct(CollectionEntry.user_id)).desc())
            .limit(50)
        ).all()
    )
    used |= {w.id for w in tier5}
    tier6 = [best_copy(k) for k in sorted(rest, key=plays, reverse=True) if either[k][1].id not in used]
    return [tier1, tier2, tier3, tier4, tier5, tier6]


async def _preview(session: Session, work: Work) -> str | None:
    if work.preview_checked_at is None:
        try:
            work.preview_url = await itunes.find_preview(work.creator or "", work.title)
        except itunes.ItunesUnavailable:
            return None  # not cached: retried next game
        work.preview_checked_at = utcnow()
        session.add(work)
        session.commit()
    return work.preview_url


def youtube_link(work: Work) -> tuple[str | None, str]:
    """(embed id or None, a watch/search URL) for listening to the whole song after the reveal."""
    if work.source == "youtube":
        return work.external_id, f"https://music.youtube.com/watch?v={work.external_id}"
    return None, "https://www.youtube.com/results?search_query=" + quote(f"{work.creator or ''} {work.title}".strip())


async def build_quiz(session: Session, p1: User, p2: User, is_friend: bool, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random()
    tiers = candidate_tiers(session, p1, p2, is_friend)
    picked: list[tuple[Work, int]] = []
    lookups = 0
    for t, tier in enumerate(tiers):
        pool = tier[:20]
        rng.shuffle(pool)  # vary games between the same two players
        for work in pool:
            if len(picked) == ROUNDS or lookups >= MAX_LOOKUPS:
                break
            if work.preview_checked_at is None:
                lookups += 1
            if await _preview(session, work):
                picked.append((work, t))
        if len(picked) == ROUNDS:
            break
    if len(picked) < ROUNDS:
        raise NotEnoughSongs

    # Decoys may come from either library (they're never the answer), plus the popular songs.
    libraries = [w for _, w in _music(session, p1, p2, is_friend).values()] + [w for _, w in _music(session, p2, p1, is_friend).values()]
    decoy_pool = list({w.id: w for w in libraries + [w for tier in tiers for w in tier]}.values())
    owners = {}
    for player, lib in ((p1, _music(session, p1, p2, is_friend)), (p2, _music(session, p2, p1, is_friend))):
        for k in lib:
            owners.setdefault(k, []).append(player.display_name)
    rounds = []
    for work, tier in picked:
        same_artist = [w for w in decoy_pool if w.id != work.id and _key(w)[0] == _key(work)[0]]
        others = [w for w in decoy_pool if w.id != work.id and w not in same_artist]
        rng.shuffle(same_artist)
        rng.shuffle(others)
        decoys, titles = [], {work.title.casefold()}
        for w in same_artist[:5] + others:  # a few same-artist decoys make it harder
            if w.title.casefold() not in titles:
                titles.add(w.title.casefold())
                decoys.append(w)
            if len(decoys) == OPTIONS - 1:
                break
        options = [{"id": w.id, "t": w.title, "a": w.creator or ""} for w in decoys + [work]]
        rng.shuffle(options)
        embed, link = youtube_link(work)
        rounds.append({"id": work.id, "t": work.title, "a": work.creator or "", "p": work.preview_url,
                       "o": options, "tier": tier, "yt": embed, "link": link,
                       "why": TIER_LABELS[tier], "own": owners.get(_key(work), [])})
    return rounds


def new_state(players: list[int], rounds: list[dict]) -> dict:
    return {"players": players, "rounds": rounds, "i": 0, "scores": {str(p): 0 for p in players}, **_round_reset(players)}


def _round_reset(players: list[int]) -> dict:
    return {"stage": 0, "acted": {}, "solved": {}, "wrong": {str(p): [] for p in players}, "ready": {}, "phase": "play"}


def _advance(state: dict) -> None:
    """Move to the next stage once both players acted; reveal when solved or out of stages."""
    players = [str(p) for p in state["players"]]
    if all(p in state["solved"] for p in players):
        state["phase"] = "reveal"
        return
    if all(p in state["solved"] or p in state["acted"] for p in players):
        if state["stage"] + 1 >= len(STAGES):
            state["phase"] = "reveal"
        else:
            state["stage"] += 1
            state["acted"] = {}


def guess(state: dict, user_id: int, choice: int) -> bool:
    me = str(user_id)
    if state["phase"] != "play" or me in state["solved"] or me in state["acted"]:
        return False
    rnd = state["rounds"][state["i"]]
    if choice not in {o["id"] for o in rnd["o"]} or choice in state["wrong"][me]:
        return False
    if choice == rnd["id"]:
        state["solved"][me] = state["stage"]
        state["scores"][me] += POINTS[state["stage"]]
    else:
        state["wrong"][me].append(choice)
        state["acted"][me] = True
    _advance(state)
    return True


def pass_stage(state: dict, user_id: int) -> bool:
    me = str(user_id)
    if state["phase"] != "play" or me in state["solved"] or me in state["acted"]:
        return False
    state["acted"][me] = True
    _advance(state)
    return True


def next_round(state: dict, user_id: int) -> bool:
    if state["phase"] != "reveal":
        return False
    state["ready"][str(user_id)] = True
    if all(str(p) in state["ready"] for p in state["players"]):
        state["i"] += 1
        if state["i"] >= len(state["rounds"]):
            state["phase"] = "done"
        else:
            state.update(_round_reset(state["players"]))
    return True
