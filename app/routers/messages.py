from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, col, select

from app import messages
from app.auth import RequiredUser
from app.db import SessionDep
from app.models import User
from app.social import blocked_ids, friend_ids
from app.templating import flash, render

router = APIRouter(prefix="/me/messages")


def _other(session: Session, me: User, username: str) -> User:
    other = session.exec(select(User).where(User.username == username.lower())).first()
    if other is None or not messages.can_message(session, me, other):
        raise HTTPException(status_code=404)
    return other


def _json(m, me: User) -> dict:
    return {"id": m.id, "mine": m.sender_id == me.id, "body": m.body, "at": m.created_at.isoformat()}


@router.get("", response_class=HTMLResponse)
def inbox(request: Request, session: SessionDep, me: RequiredUser):
    convos = messages.conversations(session, me)
    talked = {c.other.id for c in convos}
    hidden = blocked_ids(session, me.id)
    friends = [u for u in session.exec(select(User).where(col(User.id).in_(friend_ids(session, me.id) - talked - hidden)))]
    return render(request, "messages.html", me=me, convos=convos, friends=sorted(friends, key=lambda u: u.display_name.casefold()))


@router.get("/{username}", response_class=HTMLResponse)
def conversation(request: Request, session: SessionDep, me: RequiredUser, username: str):
    other = _other(session, me, username)
    history = messages.thread(session, me, other)
    messages.mark_read(session, me, other)
    return render(
        request, "conversation.html", me=me, other=other, history=history,
        openers=[] if history else messages.openers(session, me, other), MAX_MESSAGE=messages.MAX_MESSAGE,
    )


@router.post("/{username}")
def send(request: Request, session: SessionDep, me: RequiredUser, username: str, body: Annotated[str, Form()] = ""):
    other = _other(session, me, username)
    text = body.strip()
    fetch = request.headers.get("x-requested-with") == "fetch"
    if not text or len(text) > messages.MAX_MESSAGE:
        if fetch:
            return JSONResponse({"error": f"訊息請寫 1–{messages.MAX_MESSAGE} 字"}, status_code=400)
        flash(request, f"訊息請寫 1–{messages.MAX_MESSAGE} 字")
    else:
        message = messages.send(session, me, other, text)
        if fetch:
            return JSONResponse(_json(message, me))
    return RedirectResponse(f"/me/messages/{other.username}#end", status_code=303)


@router.get("/{username}/new")
def poll(session: SessionDep, me: RequiredUser, username: str, after: int = 0):
    other = _other(session, me, username)
    new = messages.thread(session, me, other, after=after)
    messages.mark_read(session, me, other)
    return {"messages": [_json(m, me) for m in new]}
