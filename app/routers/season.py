"""本季新番快速勾選 pages: /me/season (cover grid) and the 探索 banner's dismiss button."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import seasonal
from app.auth import RequiredUser, safe_next
from app.db import SessionDep
from app.models import User
from app.services import anilist
from app.templating import flash, render

router = APIRouter(prefix="/me/season")


async def _choices(session: Session, me: User, key: str) -> list[seasonal.SeasonAnime]:
    """This season's list, plus anything already picked that has since dropped off it (so saving
    never silently un-picks it)."""
    items = await seasonal.season_list(session, key)
    listed = {str(a.id) for a in items}
    extra = [
        seasonal.SeasonAnime(int(w.external_id), w.title, w.original_title, w.cover_url, w.year, None)
        for _, w in seasonal.picks(session, me.id, key)
        if w.source == "anilist" and w.external_id not in listed
    ]
    return extra + items


@router.get("", response_class=HTMLResponse)
async def pick_page(request: Request, session: SessionDep, me: RequiredUser, next: str = ""):
    key = seasonal.current_key()
    back = safe_next(next, "/me/collection#anime")
    try:
        items = await _choices(session, me, key)
        error = None if items else "AniList 還沒有這一季的新番資料"
    except anilist.AniListError:
        items, error = [], "AniList 暫時無法連線，請稍後再試"
    picked = {int(w.external_id) for _, w in seasonal.picks(session, me.id, key) if w.source == "anilist"}
    return render(
        request, "season.html", me=me, items=items, picked=picked, error=error,
        season_label=seasonal.label(key), next=next, back=back,
    )


@router.post("")
async def save_picks(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    wanted = {int(v) for v in form.getlist("pick") if str(v).isdigit()}
    key = seasonal.current_key()
    try:
        items = await _choices(session, me, key)
    except anilist.AniListError:
        flash(request, "AniList 暫時無法連線，這次沒有儲存，請稍後再試")
        return RedirectResponse("/me/season", status_code=303)
    chosen = [a for a in items if a.id in wanted]
    result = seasonal.save(session, me, key, chosen)
    if me.season_banner_dismissed != key:  # picked this season: the 探索 banner has done its job
        seasonal.dismiss_banner(session, me)
    flash(request, f"已更新 {seasonal.label(key)}在追：{len(chosen)} 部" + (f"（移除 {result.removed} 部）" if result.removed else ""))
    return RedirectResponse(safe_next(str(form.get("next") or ""), f"/u/{me.username}#anime"), status_code=303)


@router.post("/banner/dismiss")
def dismiss_banner(request: Request, session: SessionDep, me: RequiredUser, next: Annotated[str, Form()] = ""):
    seasonal.dismiss_banner(session, me)
    if request.headers.get("x-requested-with") == "fetch":
        return HTMLResponse(status_code=204)
    return RedirectResponse(safe_next(next, "/match"), status_code=303)
