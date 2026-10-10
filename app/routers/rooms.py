"""Live multiplayer games: 猜誰是臥底 and 猜歌. Pages poll /v and reload when the room changes."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session

from app import rooms, songquiz, undercover
from app.auth import RequiredUser
from app.db import SessionDep
from app.models import GameRoom, User
from app.social import are_friends, is_blocked
from app.templating import flash, render

router = APIRouter(prefix="/games")


def _room_or_404(session: Session, code: str, kind: str) -> GameRoom:
    room = rooms.get_room(session, code, kind)
    if room is None:
        raise HTTPException(status_code=404)
    return room


def _member(session: Session, room: GameRoom, me: User) -> None:
    if not rooms.is_player(session, room, me):
        raise HTTPException(status_code=403)


def _back(kind: str, room: GameRoom) -> RedirectResponse:
    return RedirectResponse(f"/games/{kind}/{room.code}", status_code=303)


@router.get("/room/{kind}/{code}/v")
def room_version(session: SessionDep, me: RequiredUser, kind: str, code: str):
    room = _room_or_404(session, code, kind)
    return JSONResponse({"v": rooms.version(room)})


# ---------- 猜誰是臥底 ----------

@router.get("/undercover", response_class=HTMLResponse)
def undercover_home(request: Request, me: RequiredUser):
    return render(request, "undercover_home.html", me=me, themes=undercover.THEMES)


@router.post("/undercover/new")
def undercover_new(session: SessionDep, me: RequiredUser, theme: Annotated[str, Form()] = "characters"):
    theme = theme if theme in undercover.THEMES else "characters"
    room = rooms.create_room(session, me, "undercover", {"theme": theme})
    return _back("undercover", room)


@router.post("/undercover/join")
def undercover_join_code(request: Request, code: Annotated[str, Form()], me: RequiredUser):
    return RedirectResponse(f"/games/undercover/{code.strip().upper()}", status_code=303)


@router.get("/undercover/{code}", response_class=HTMLResponse)
def undercover_room(request: Request, session: SessionDep, me: RequiredUser, code: str):
    room = rooms.get_room(session, code, "undercover")
    if room is None:
        flash(request, "找不到這個房間，代碼可能打錯或已過期")
        return RedirectResponse("/games/undercover", status_code=303)
    people = rooms.players(session, room)
    joined = any(p.id == me.id for p in people)
    if not joined:
        host = session.get(User, room.host_id)
        if room.status != "lobby":
            flash(request, "這局已經開始了，等下一局再加入")
            return RedirectResponse("/games/undercover", status_code=303)
        if len(people) >= undercover.MAX_PLAYERS:
            flash(request, "房間已滿")
            return RedirectResponse("/games/undercover", status_code=303)
        if host and is_blocked(session, me.id, host.id):
            raise HTTPException(status_code=404)
        rooms.join(session, room, me)
        people = rooms.players(session, room)

    state = rooms.load(room)
    by_id = {p.id: p for p in people}
    ctx = dict(
        me=me, room=room, state=state, people=people, by_id=by_id, is_host=room.host_id == me.id,
        themes=undercover.THEMES, results=undercover.RESULTS, MIN=undercover.MIN_PLAYERS, MAX=undercover.MAX_PLAYERS,
        MAX_DESC=undercover.MAX_DESC, version=rooms.version(room),
    )
    if room.status != "lobby":
        ctx.update(
            mine=undercover.my_word(state, me.id),
            speaker=state["order"][state["turn"]] if room.status == "describe" else None,
            voted=str(me.id) in state["votes"],
            vote_counts={uid: list(state["votes"].values()).count(uid) for uid in state["order"]},
        )
    return render(request, "undercover.html", **ctx)


@router.post("/undercover/{code}/theme")
def undercover_theme(session: SessionDep, me: RequiredUser, code: str, theme: Annotated[str, Form()]):
    room = _room_or_404(session, code, "undercover")
    if room.host_id == me.id and room.status == "lobby" and theme in undercover.THEMES:
        state = rooms.load(room)
        state["theme"] = theme
        rooms.save(session, room, state)
    return _back("undercover", room)


@router.post("/undercover/{code}/start")
async def undercover_start(request: Request, session: SessionDep, me: RequiredUser, code: str):
    room = _room_or_404(session, code, "undercover")
    if room.host_id != me.id or room.status not in ("lobby", "done"):
        raise HTTPException(status_code=403)
    people = rooms.players(session, room)
    if len(people) < undercover.MIN_PLAYERS:
        flash(request, f"至少要 {undercover.MIN_PLAYERS} 個人才能開始")
        return _back("undercover", room)
    try:
        state = await undercover.deal(session, people, rooms.load(room).get("theme", "characters"))
    except undercover.NotEnough:
        flash(request, "大家的收藏還不夠湊滿 16 格，換個主題或多加點收藏再試")
        return _back("undercover", room)
    rooms.save(session, room, state, "describe")
    return _back("undercover", room)


@router.post("/undercover/{code}/describe")
def undercover_describe(session: SessionDep, me: RequiredUser, code: str, text: Annotated[str, Form()] = ""):
    room = _room_or_404(session, code, "undercover")
    _member(session, room, me)
    state = rooms.load(room)
    if room.status == "describe":
        everyone_spoke = undercover.describe(state, me.id, text)
        rooms.save(session, room, state, "vote" if everyone_spoke else None)
    return _back("undercover", room)


@router.post("/undercover/{code}/vote")
def undercover_vote(session: SessionDep, me: RequiredUser, code: str, target: Annotated[int, Form()]):
    room = _room_or_404(session, code, "undercover")
    _member(session, room, me)
    state = rooms.load(room)
    if room.status == "vote" and str(me.id) not in state["votes"]:
        if undercover.vote(state, me.id, target):
            rooms.save(session, room, state, undercover.tally(state))
        else:
            rooms.save(session, room, state)
    return _back("undercover", room)


@router.post("/undercover/{code}/guess")
def undercover_guess(session: SessionDep, me: RequiredUser, code: str, index: Annotated[int, Form()]):
    room = _room_or_404(session, code, "undercover")
    _member(session, room, me)
    state = rooms.load(room)
    if room.status == "guess" and undercover.spy_guess(state, me.id, index):
        rooms.save(session, room, state, "done")
    return _back("undercover", room)


# ---------- 猜歌 (live 1-on-1) ----------

def _song_room_page(request: Request, session: Session, me: User, code: str):
    room = rooms.get_room(session, code, "song")
    if room is None:
        flash(request, "找不到這個房間，代碼可能打錯或已過期")
        return None, RedirectResponse("/games/song", status_code=303)
    people = rooms.players(session, room)
    if not any(p.id == me.id for p in people):
        host = session.get(User, room.host_id)
        if room.status != "lobby" or len(people) >= 2:
            flash(request, "這個房間已經滿了")
            return None, RedirectResponse("/games/song", status_code=303)
        if host and is_blocked(session, me.id, host.id):
            raise HTTPException(status_code=404)
        rooms.join(session, room, me)
    return room, None


@router.get("/song", response_class=HTMLResponse)
def song_home(request: Request, me: RequiredUser):
    return render(request, "song_home.html", me=me, STAGES=songquiz.STAGES, POINTS=songquiz.POINTS)


@router.post("/song/new")
def song_new(session: SessionDep, me: RequiredUser):
    room = rooms.create_room(session, me, "song")
    return _back("song", room)


@router.post("/song/join")
def song_join_code(code: Annotated[str, Form()], me: RequiredUser):
    return RedirectResponse(f"/games/song/{code.strip().upper()}", status_code=303)


@router.get("/song/{code}", response_class=HTMLResponse)
def song_room(request: Request, session: SessionDep, me: RequiredUser, code: str):
    room, redirect = _song_room_page(request, session, me, code)
    if redirect:
        return redirect
    people = rooms.players(session, room)
    state = rooms.load(room)
    ctx = dict(me=me, room=room, state=state, people=people, by_id={p.id: p for p in people},
               is_host=room.host_id == me.id, version=rooms.version(room), STAGES=songquiz.STAGES,
               POINTS=songquiz.POINTS, ROUNDS=songquiz.ROUNDS)
    if room.status == "playing":
        rnd = state["rounds"][min(state["i"], len(state["rounds"]) - 1)]
        opponent = next((p for p in people if p.id != me.id), None)
        ctx.update(rnd=rnd, mine=str(me.id), opponent=opponent, theirs=str(opponent.id) if opponent else None)
    return render(request, "song.html", **ctx)


@router.post("/song/{code}/start")
async def song_start(request: Request, session: SessionDep, me: RequiredUser, code: str):
    room = _room_or_404(session, code, "song")
    if room.host_id != me.id or room.status not in ("lobby", "done"):
        raise HTTPException(status_code=403)
    people = rooms.players(session, room)
    if len(people) != 2:
        flash(request, "要兩個人才能開始")
        return _back("song", room)
    a, b = people
    try:
        quiz = await songquiz.build_quiz(session, a, b, are_friends(session, a.id, b.id))
    except songquiz.NotEnoughSongs:
        flash(request, "找不到足夠你們都可能聽過、而且有試聽片段的歌。多匯入一些音樂再試試")
        return _back("song", room)
    rooms.save(session, room, songquiz.new_state([a.id, b.id], quiz), "playing")
    return _back("song", room)


def _song_action(session: Session, me: User, code: str, action) -> RedirectResponse:
    room = _room_or_404(session, code, "song")
    _member(session, room, me)
    state = rooms.load(room)
    if room.status == "playing" and action(state):
        rooms.save(session, room, state, "done" if state["phase"] == "done" else None)
    return _back("song", room)


@router.post("/song/{code}/guess")
def song_guess(session: SessionDep, me: RequiredUser, code: str, choice: Annotated[int, Form()]):
    return _song_action(session, me, code, lambda st: songquiz.guess(st, me.id, choice))


@router.post("/song/{code}/pass")
def song_pass(session: SessionDep, me: RequiredUser, code: str):
    return _song_action(session, me, code, lambda st: songquiz.pass_stage(st, me.id))


@router.post("/song/{code}/next")
def song_next(session: SessionDep, me: RequiredUser, code: str):
    return _song_action(session, me, code, lambda st: songquiz.next_round(st, me.id))
