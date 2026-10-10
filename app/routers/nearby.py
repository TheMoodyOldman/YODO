from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import select

from app import messages, nearby
from app.auth import RequiredUser, VerifiedUser, is_locked
from app.db import SessionDep
from app.models import Message, NearbyPost, NearbyReply, User
from app.social import is_blocked
from app.templating import flash, render

router = APIRouter(prefix="/nearby")

# The viewer's coarse location lives only in the (signed) session cookie, never in the database.
SESSION_KEY = "nearby_at"


def _where(request: Request) -> tuple[float, float] | None:
    at = request.session.get(SESSION_KEY)
    return (at["lat"], at["lon"]) if at else None


@router.get("", response_class=HTMLResponse)
def page(request: Request, session: SessionDep, me: RequiredUser):
    where = _where(request)
    items = nearby.around(session, me, where) if where else []
    for item in items:
        item.shared = [w.title for w in messages.shared_works(session, me, item.author, limit=3)]
    mine = nearby.my_post(session, me)
    return render(
        request, "nearby.html", me=me, where=where, place=(request.session.get(SESSION_KEY) or {}).get("label"),
        items=items, mine=mine, responders=nearby.responders(session, mine, me) if mine else [],
        hours_left=nearby.hours_left(mine) if mine else 0,
        REGIONS=list(nearby.REGION_CENTERS), RADII=nearby.RADII, DEFAULT_RADIUS=nearby.DEFAULT_RADIUS,
        MAX_BODY=nearby.MAX_BODY, MAX_REPLY=nearby.MAX_REPLY, POST_HOURS=nearby.POST_HOURS,
    )


@router.post("/location")
async def set_location(request: Request, me: RequiredUser):
    """Either {lat, lon} from the browser (rounded here again) or a region name."""
    form = await request.form()
    region = str(form.get("region", ""))
    if region:
        if region not in nearby.REGION_CENTERS:
            raise HTTPException(status_code=400)
        at, label = nearby.REGION_CENTERS[region], f"{region}（市中心）"
    else:
        try:
            at = nearby.coarse(float(form.get("lat", "")), float(form.get("lon", "")))
        except ValueError:
            at = None
        if at is None:
            raise HTTPException(status_code=400)
        label = "目前位置（約略到 1 公里）"
    request.session[SESSION_KEY] = {"lat": at[0], "lon": at[1], "label": label}
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse("/nearby", status_code=303)


@router.post("/forget")
def forget(request: Request, me: RequiredUser):
    request.session.pop(SESSION_KEY, None)
    flash(request, "已清除位置")
    return RedirectResponse("/nearby", status_code=303)


@router.post("")
def post(request: Request, session: SessionDep, me: VerifiedUser,
         body: Annotated[str, Form()] = "", radius: Annotated[int, Form()] = nearby.DEFAULT_RADIUS):
    where = _where(request)
    text = body.strip()
    if where is None:
        flash(request, "請先選擇位置")
    elif not text or len(text) > nearby.MAX_BODY:
        flash(request, f"訊息請寫 1–{nearby.MAX_BODY} 字")
    else:
        nearby.publish(session, me, where, radius if radius in nearby.RADII else nearby.DEFAULT_RADIUS, text)
        flash(request, f"已發布，{nearby.POST_HOURS} 小時內附近的人看得到")
    return RedirectResponse("/nearby", status_code=303)


@router.post("/{post_id}/cancel")
def cancel(request: Request, session: SessionDep, me: RequiredUser, post_id: int):
    item = session.get(NearbyPost, post_id)
    if item is None or item.user_id != me.id:
        raise HTTPException(status_code=404)
    item.cancelled = True
    session.add(item)
    session.commit()
    flash(request, "已收回，附近的人不會再看到這則訊息")
    return RedirectResponse("/nearby", status_code=303)


@router.post("/{post_id}/reply")
def reply(request: Request, session: SessionDep, me: VerifiedUser, post_id: int, body: Annotated[str, Form()] = ""):
    where = _where(request)
    item = session.get(NearbyPost, post_id)
    author = session.get(User, item.user_id) if item else None
    visible = where is not None and author is not None and any(i.post.id == post_id for i in nearby.around(session, me, where))
    if not visible or is_locked(author) or is_blocked(session, me.id, author.id):
        raise HTTPException(status_code=404)
    text = body.strip()
    if not text or len(text) > nearby.MAX_REPLY:
        flash(request, f"回應請寫 1–{nearby.MAX_REPLY} 字")
        return RedirectResponse("/nearby", status_code=303)
    if session.exec(select(NearbyReply).where(NearbyReply.post_id == post_id, NearbyReply.user_id == me.id)).first() is None:
        session.add(NearbyReply(post_id=post_id, user_id=me.id, body=text))
        # The opening message carries their post and your answer, so the chat has context.
        session.add(Message(sender_id=author.id, recipient_id=me.id, body=f"（附近）{item.body}", read_at=item.created_at))
        session.add(Message(sender_id=me.id, recipient_id=author.id, body=text))
        session.commit()
    return RedirectResponse(f"/me/messages/{author.username}", status_code=303)
