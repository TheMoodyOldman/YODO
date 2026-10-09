import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlmodel import func, select

from app.auth import RequiredUser
from app.config import settings
from app.db import SessionDep
from app.models import User
from app.music import LASTFM, clear_source
from app.services import lastfm
from app.sync import sync_lastfm
from app.templating import flash

router = APIRouter(prefix="/me/lastfm")

BACK = "/me/collection#music"
PRIVATE_MSG = "你的 Last.fm 隱藏了收聽紀錄。請到 Last.fm 設定 → 隱私，取消「隱藏最近收聽資訊」後再同步一次。"
ERROR_MSG = "Last.fm 暫時無法連線，請稍後再試"


async def _sync_and_redirect(request: Request, session: SessionDep, me: User) -> RedirectResponse:
    try:
        result = await sync_lastfm(session, me)
    except lastfm.LastfmPrivate:
        flash(request, PRIVATE_MSG)
        return RedirectResponse(BACK, status_code=303)
    except lastfm.LastfmError:
        flash(request, ERROR_MSG)
        return RedirectResponse(BACK, status_code=303)

    r = result.imported
    summary = f"Last.fm 同步完成：{r.songs_with_plays} 首有播放紀錄，共 {r.total_plays} 次播放"
    if result.truncated:
        summary += "（紀錄太多，最早的月份可能不完整）"
    if r.new_songs:
        flash(request, f"{summary}。新增 {r.new_songs} 首歌，確認後才會公開")
        return RedirectResponse("/me/music/review", status_code=303)
    flash(request, f"{summary}，沒有新的歌曲")
    return RedirectResponse(BACK, status_code=303)


def _callback_url(request: Request, state: str) -> str:
    return f"{request.url_for('lastfm_callback')}?state={state}"


@router.get("/connect")
def connect(request: Request, me: RequiredUser):
    if not (settings.lastfm_api_key and settings.lastfm_shared_secret):
        flash(request, "伺服器尚未設定 LASTFM_API_KEY 與 LASTFM_SHARED_SECRET")
        return RedirectResponse(BACK, status_code=303)
    state = secrets.token_urlsafe(16)
    request.session["lastfm_state"] = state
    return RedirectResponse(lastfm.auth_url(_callback_url(request, state)), status_code=303)


@router.get("/callback", name="lastfm_callback")
async def callback(request: Request, session: SessionDep, me: RequiredUser, state: str = "", token: str = ""):
    expected = request.session.pop("lastfm_state", None)
    if not expected or not secrets.compare_digest(state, expected) or not token:
        flash(request, "Last.fm 連結已失效，請再試一次")
        return RedirectResponse(BACK, status_code=303)

    try:
        username = await lastfm.get_session_username(token)
    except lastfm.LastfmError:
        username = None
    if not username:
        flash(request, "Last.fm 連結驗證失敗，請再試一次")
        return RedirectResponse(BACK, status_code=303)

    taken = session.exec(
        select(User).where(func.lower(User.lastfm_username) == username.lower(), User.id != me.id)
    ).first()
    if taken:
        flash(request, "這個 Last.fm 帳號已經連結到其他使用者")
        return RedirectResponse(BACK, status_code=303)

    if me.lastfm_username and me.lastfm_username.lower() != username.lower():
        me.lastfm_synced_at = None  # different account: start over with a full first sync
    me.lastfm_username = username
    session.add(me)
    session.commit()
    return await _sync_and_redirect(request, session, me)


@router.post("/sync")
async def sync(request: Request, session: SessionDep, me: RequiredUser):
    if not me.lastfm_username:
        return RedirectResponse("/me/lastfm/connect", status_code=303)
    return await _sync_and_redirect(request, session, me)


@router.post("/unlink")
def unlink(request: Request, session: SessionDep, me: RequiredUser):
    me.lastfm_username = None
    me.lastfm_synced_at = None
    session.add(me)
    session.commit()
    flash(request, "已解除 Last.fm 連結，已匯入的歌曲仍保留在收藏中")
    return RedirectResponse(BACK, status_code=303)


@router.post("/clear")
def clear(request: Request, session: SessionDep, me: RequiredUser):
    removed = clear_source(session, me, LASTFM)
    me.lastfm_synced_at = None  # next sync re-imports from scratch
    session.add(me)
    session.commit()
    flash(request, f"已刪除 {removed} 首從 Last.fm 匯入的歌曲與播放紀錄")
    return RedirectResponse(BACK, status_code=303)
