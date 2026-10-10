from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, col, select

from app.auth import RequiredUser, is_locked
from app.card_render import fetch_images
from app.db import SessionDep
from app.game_cards import (
    render_bingo_card,
    render_challenge_card,
    render_challenge_day_card,
    render_compat_card,
    render_guess_card,
)
from app.games import (
    FREE,
    GUESS_ROUNDS,
    PROMPT_BY_KEY,
    bingo_board,
    bingo_lines,
    bingo_marked,
    compatibility,
    current_month,
    guess_label,
    new_guess_game,
)
from app.activity import record
from app.challenge import DAYS as CHALLENGE_DAYS
from app.challenge import PROMPTS as CHALLENGE_PROMPTS
from app.challenge import TITLES as CHALLENGE_TITLES
from app.challenge import get_challenge, owned_entry, parse_kind, search_collection, unlocked_days
from app.challenge import picks as challenge_picks
from app.challenge import today as challenge_today
from app.models import ActivityKind, BingoMark, Category, Challenge, ChallengePick, User, Work
from app.social import Relation, relation
from app.templating import render

router = APIRouter(prefix="/games")

JPEG_HEADERS = {"Cache-Control": "private, max-age=60"}


def _jpeg(data: bytes, filename: str) -> Response:
    return Response(data, media_type="image/jpeg", headers={**JPEG_HEADERS, "Content-Disposition": f'inline; filename="{filename}"'})


def _footer(request: Request, user: User) -> str:
    return f"{request.url.netloc}/u/{user.username}"


@router.get("", response_class=HTMLResponse)
def hub(request: Request, me: RequiredUser):
    return render(request, "games.html", me=me)


# ---------- 品味契合度挑戰 ----------

def _other(session: Session, me: User, username: str) -> tuple[User, bool]:
    other = session.exec(select(User).where(User.username == username.lower())).first()
    if other is None or other.id == me.id or is_locked(other):
        raise HTTPException(status_code=404)
    rel = relation(session, me, other)
    if rel == Relation.blocked:
        raise HTTPException(status_code=404)
    return other, rel == Relation.friends


@router.get("/compat/{username}", response_class=HTMLResponse)
def compat_page(request: Request, session: SessionDep, me: RequiredUser, username: str, guess: str = ""):
    other, is_friend = _other(session, me, username)
    if not guess:  # the "challenge": commit to a guess before seeing the answer
        return render(request, "compat.html", me=me, other=other, result=None)
    result = compatibility(session, me, other, is_friend)
    guessed = int(guess) if guess.isdigit() and 0 <= int(guess) <= 100 else None
    return render(
        request,
        "compat.html",
        me=me,
        other=other,
        result=result,
        guessed=guessed,
        off_by=abs(guessed - result.pct) if guessed is not None else None,
        card_url=f"/games/compat/{other.username}/card.jpg",
    )


@router.get("/compat/{username}/card.jpg")
async def compat_card(request: Request, session: SessionDep, me: RequiredUser, username: str):
    other, is_friend = _other(session, me, username)
    result = compatibility(session, me, other, is_friend)
    images = await fetch_images({w.cover_url for w, _, _ in result.shared[:4] if w.cover_url})
    data = await run_in_threadpool(render_compat_card, me, other, result, images, _footer(request, me))
    return _jpeg(data, f"yodo-compat-{other.username}.jpg")


# ---------- 猜猜這是誰的收藏 ----------

def _guess_state(request: Request) -> dict | None:
    return request.session.get("guess")


@router.get("/guess", response_class=HTMLResponse)
def guess_page(request: Request, session: SessionDep, me: RequiredUser):
    state = _guess_state(request)
    if state is None or state.get("u") != me.id:
        rounds = new_guess_game(session, me)
        if rounds is None:
            return render(request, "guess.html", me=me, not_enough=True)
        state = {"u": me.id, "r": rounds, "i": 0, "s": 0, "fb": None}
        request.session["guess"] = state

    feedback = state.get("fb")
    users_needed = {feedback["a"], feedback["c"]} if feedback else set()
    finished = state["i"] >= len(state["r"])
    question = None
    if not finished:
        rnd = state["r"][state["i"]]
        works = {w.id: w for w in session.exec(select(Work).where(col(Work.id).in_(rnd["w"])))}
        users_needed |= set(rnd["o"])
        question = {"works": [works[w] for w in rnd["w"] if w in works], "options": rnd["o"]}
    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(users_needed)))} if users_needed else {}
    return render(
        request,
        "guess.html",
        me=me,
        state=state,
        question=question,
        users=users,
        feedback=feedback,
        finished=finished,
        total=len(state["r"]),
        label=guess_label(state["s"]) if finished else None,
    )


@router.post("/guess/answer")
def guess_answer(request: Request, me: RequiredUser, choice: Annotated[int, Form()]):
    state = _guess_state(request)
    if not state or state.get("u") != me.id or state["i"] >= len(state["r"]):
        return RedirectResponse("/games/guess", status_code=303)
    rnd = state["r"][state["i"]]
    if choice not in rnd["o"]:
        return RedirectResponse("/games/guess", status_code=303)
    correct = choice == rnd["a"]
    state["s"] += int(correct)
    state["fb"] = {"ok": correct, "a": rnd["a"], "c": choice}
    state["i"] += 1
    request.session["guess"] = state
    return RedirectResponse("/games/guess", status_code=303)


@router.post("/guess/new")
def guess_new(request: Request, me: RequiredUser):
    request.session.pop("guess", None)
    return RedirectResponse("/games/guess", status_code=303)


@router.get("/guess/card.jpg")
async def guess_card(request: Request, me: RequiredUser):
    state = _guess_state(request)
    if not state or state.get("u") != me.id or state["i"] < len(state["r"]):
        raise HTTPException(status_code=404)
    data = await run_in_threadpool(render_guess_card, me, state["s"], len(state["r"]), guess_label(state["s"]), _footer(request, me))
    return _jpeg(data, "yodo-guess.jpg")


# ---------- 興趣賓果 ----------

@router.get("/bingo", response_class=HTMLResponse)
def bingo_page(request: Request, session: SessionDep, me: RequiredUser):
    month = current_month()
    board = bingo_board(me, month)
    marked = bingo_marked(session, me, month, board)
    cells = [
        {"key": key, "text": "FREE" if key == FREE else PROMPT_BY_KEY[key].text,
         "auto": key == FREE or PROMPT_BY_KEY[key].auto is not None, "marked": m}
        for key, m in zip(board, marked)
    ]
    return render(request, "bingo.html", me=me, cells=cells, lines=bingo_lines(marked), month=month,
                  marked_count=sum(marked) - 1, card_url=f"/games/bingo/card.jpg?m={month}")


@router.post("/bingo/toggle")
def bingo_toggle(request: Request, session: SessionDep, me: RequiredUser, key: Annotated[str, Form()]):
    month = current_month()
    board = bingo_board(me, month)
    prompt = PROMPT_BY_KEY.get(key)
    if key not in board or prompt is None or prompt.auto is not None:
        raise HTTPException(status_code=400)  # auto squares follow the data, FREE is always on
    row = session.exec(select(BingoMark).where(BingoMark.user_id == me.id, BingoMark.month == month, BingoMark.key == key)).first()
    if row:
        session.delete(row)
    else:
        session.add(BingoMark(user_id=me.id, month=month, key=key))
    session.commit()
    if request.headers.get("x-requested-with") == "fetch":
        marked = bingo_marked(session, me, month, board)
        return JSONResponse({"marked": row is None, "lines": bingo_lines(marked), "count": sum(marked) - 1})
    return RedirectResponse("/games/bingo", status_code=303)


@router.get("/bingo/card.jpg")
async def bingo_card(request: Request, session: SessionDep, me: RequiredUser):
    month = current_month()
    board = bingo_board(me, month)
    marked = bingo_marked(session, me, month, board)
    data = await run_in_threadpool(render_bingo_card, me, month, board, marked, bingo_lines(marked), _footer(request, me))
    return _jpeg(data, f"yodo-bingo-{month}.jpg")


# ---------- 30 天挑戰 ----------

def _kind_or_404(kind: str):
    category = parse_kind(kind)
    if category is None:
        raise HTTPException(status_code=404)
    return category


@router.get("/challenge", response_class=HTMLResponse)
def challenge_index(request: Request, session: SessionDep, me: RequiredUser):
    runs = []
    for category in (Category.music, Category.anime, Category.game):
        ch = get_challenge(session, me, category)
        runs.append({"kind": category, "title": CHALLENGE_TITLES[category], "challenge": ch,
                     "done": len(challenge_picks(session, ch)) if ch else 0, "open": unlocked_days(ch) if ch else 0})
    return render(request, "challenge_index.html", me=me, runs=runs, DAYS=CHALLENGE_DAYS)


@router.get("/challenge/{kind}", response_class=HTMLResponse)
def challenge_page(request: Request, session: SessionDep, me: RequiredUser, kind: str):
    category = _kind_or_404(kind)
    ch = get_challenge(session, me, category)
    chosen = challenge_picks(session, ch) if ch else {}
    open_days = unlocked_days(ch) if ch else 0
    latest = max(chosen, default=None)
    return render(
        request,
        "challenge.html",
        me=me,
        kind=category,
        title=CHALLENGE_TITLES[category],
        challenge=ch,
        prompts=CHALLENGE_PROMPTS[category],
        picks=chosen,
        open_days=open_days,
        latest=latest,
        DAYS=CHALLENGE_DAYS,
    )


@router.post("/challenge/{kind}/start")
def challenge_start(session: SessionDep, me: RequiredUser, kind: str, restart: Annotated[bool, Form()] = False):
    category = _kind_or_404(kind)
    ch = get_challenge(session, me, category)
    if ch and restart:
        for p in session.exec(select(ChallengePick).where(ChallengePick.challenge_id == ch.id)):
            session.delete(p)
        ch.started_on = challenge_today()
        session.add(ch)
    elif ch is None:
        session.add(Challenge(user_id=me.id, kind=category.value, started_on=challenge_today()))
    session.commit()
    return RedirectResponse(f"/games/challenge/{category.value}", status_code=303)


@router.get("/challenge/{kind}/options")
def challenge_options(session: SessionDep, me: RequiredUser, kind: str, q: str = ""):
    category = _kind_or_404(kind)
    return [
        {"id": w.id, "title": w.title, "sub": w.creator or w.original_title or "", "cover": w.cover_url or ""}
        for _, w in search_collection(session, me, category, q)
    ]


@router.post("/challenge/{kind}/pick")
def challenge_pick(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    kind: str,
    day: Annotated[int, Form()],
    work_id: Annotated[int, Form()] = 0,
):
    category = _kind_or_404(kind)
    ch = get_challenge(session, me, category)
    if ch is None or not 1 <= day <= unlocked_days(ch):
        raise HTTPException(status_code=400)  # not started, or a day that hasn't unlocked yet
    row = session.exec(select(ChallengePick).where(ChallengePick.challenge_id == ch.id, ChallengePick.day == day)).first()
    if work_id == 0:  # clear the square
        if row:
            session.delete(row)
            session.commit()
        return JSONResponse({"ok": True}) if request.headers.get("x-requested-with") == "fetch" else RedirectResponse(
            f"/games/challenge/{category.value}", status_code=303)
    if owned_entry(session, me, category, work_id) is None:
        raise HTTPException(status_code=400)
    if row is None:
        row = ChallengePick(challenge_id=ch.id, day=day, work_id=work_id)
    row.work_id = work_id
    session.add(row)
    act = record(session, me.id, ActivityKind.challenge, work_id)
    act.note = f"{category.value}:{day}"
    session.commit()
    if request.headers.get("x-requested-with") == "fetch":
        work = session.get(Work, work_id)
        return JSONResponse({"ok": True, "title": work.title, "cover": work.cover_url or ""})
    return RedirectResponse(f"/games/challenge/{category.value}#day-{day}", status_code=303)


@router.get("/challenge/{kind}/card.jpg")
async def challenge_card(request: Request, session: SessionDep, me: RequiredUser, kind: str):
    category = _kind_or_404(kind)
    ch = get_challenge(session, me, category)
    if ch is None:
        raise HTTPException(status_code=404)
    chosen = challenge_picks(session, ch)
    images = await fetch_images({w.cover_url for w in chosen.values() if w.cover_url})
    data = await run_in_threadpool(render_challenge_card, me, category, chosen, images, _footer(request, me))
    return _jpeg(data, f"yodo-30days-{category.value}.jpg")


@router.get("/challenge/{kind}/day/{day}.jpg")
async def challenge_day_card(request: Request, session: SessionDep, me: RequiredUser, kind: str, day: int):
    category = _kind_or_404(kind)
    ch = get_challenge(session, me, category)
    work = challenge_picks(session, ch).get(day) if ch else None
    if work is None:
        raise HTTPException(status_code=404)
    images = await fetch_images({work.cover_url} if work.cover_url else set())
    data = await run_in_threadpool(render_challenge_day_card, me, category, day, work, images, _footer(request, me))
    return _jpeg(data, f"yodo-30days-{category.value}-day{day}.jpg")
