import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import col, select

from app.auth import RequiredUser
from app.db import SessionDep
from app.models import Category, CollectionEntry, User, Work
from app.services import steam
from app.sync import MIN_PLAYTIME_MINUTES, sync_steam
from app.templating import flash, render

router = APIRouter(prefix="/me/steam")

BACK = "/me/collection#game"

PRIVATE_MSG = "你的 Steam「遊戲詳細資料」不是公開的，請到 Steam 個人檔案的隱私設定改成公開後再同步一次。"
ERROR_MSG = "Steam 暫時無法連線，請稍後再試"


async def _sync_and_redirect(request: Request, session: SessionDep, me: User) -> RedirectResponse:
    try:
        result = await sync_steam(session, me)
    except steam.SteamError:
        flash(request, ERROR_MSG)
        return RedirectResponse(BACK, status_code=303)
    if result is None:
        flash(request, PRIVATE_MSG)
        return RedirectResponse(BACK, status_code=303)
    if result.added:
        flash(request, f"找到 {result.added} 款新遊戲，確認後才會公開")
        return RedirectResponse("/me/steam/review", status_code=303)
    flash(request, f"同步完成，更新了 {result.updated} 款遊戲的遊玩時數" if result.updated else "同步完成，沒有新的遊戲")
    return RedirectResponse(BACK, status_code=303)


def _callback_url(request: Request, state: str) -> str:
    return f"{request.url_for('steam_callback')}?state={state}"


@router.get("/connect")
def connect(request: Request, me: RequiredUser):
    state = secrets.token_urlsafe(16)
    request.session["steam_state"] = state
    realm = str(request.base_url)
    return RedirectResponse(steam.openid_login_url(_callback_url(request, state), realm), status_code=303)


@router.get("/callback", name="steam_callback")
async def callback(request: Request, session: SessionDep, me: RequiredUser, state: str = ""):
    expected = request.session.pop("steam_state", None)
    params = dict(request.query_params)
    if not expected or not secrets.compare_digest(state, expected):
        flash(request, "Steam 連結已失效，請再試一次")
        return RedirectResponse(BACK, status_code=303)
    if params.get("openid.return_to") != _callback_url(request, state):
        flash(request, "Steam 連結驗證失敗，請再試一次")
        return RedirectResponse(BACK, status_code=303)

    try:
        steam_id = await steam.verify_openid(params)
    except steam.SteamError:
        flash(request, ERROR_MSG)
        return RedirectResponse(BACK, status_code=303)
    if steam_id is None:
        flash(request, "Steam 連結驗證失敗，請再試一次")
        return RedirectResponse(BACK, status_code=303)

    taken = session.exec(select(User).where(User.steam_id == steam_id, User.id != me.id)).first()
    if taken:
        flash(request, "這個 Steam 帳號已經連結到其他使用者")
        return RedirectResponse(BACK, status_code=303)

    me.steam_id = steam_id
    session.add(me)
    session.commit()
    return await _sync_and_redirect(request, session, me)


@router.post("/sync")
async def sync(request: Request, session: SessionDep, me: RequiredUser):
    if not me.steam_id:
        return RedirectResponse("/me/steam/connect", status_code=303)
    return await _sync_and_redirect(request, session, me)


@router.post("/unlink")
def unlink(request: Request, session: SessionDep, me: RequiredUser):
    me.steam_id = None
    session.add(me)
    session.commit()
    flash(request, "已解除 Steam 連結，已匯入的遊戲仍保留在收藏中")
    return RedirectResponse(BACK, status_code=303)


def _pending(session: SessionDep, me: User):
    return session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(
            CollectionEntry.user_id == me.id,
            Work.category == Category.game,
            col(CollectionEntry.pending_review).is_(True),
        )
        .order_by(col(CollectionEntry.playtime_minutes).desc().nulls_last())
    ).all()


@router.get("/review", response_class=HTMLResponse)
def review(request: Request, session: SessionDep, me: RequiredUser):
    rows = _pending(session, me)
    if not rows:
        return RedirectResponse(BACK, status_code=303)
    return render(request, "steam_review.html", me=me, rows=rows, min_hours=MIN_PLAYTIME_MINUTES // 60)


@router.post("/review")
async def submit_review(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    publish = {int(v) for v in form.getlist("publish") if str(v).isdigit()}
    shown = 0
    for entry, _ in _pending(session, me):
        entry.pending_review = False
        entry.hidden = entry.id not in publish
        shown += not entry.hidden
        session.add(entry)
    session.commit()
    flash(request, f"已公開 {shown} 款遊戲，其餘設為隱藏，之後可在收藏中調整")
    return RedirectResponse(BACK, status_code=303)
