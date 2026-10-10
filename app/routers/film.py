from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import col, select

from app.auth import RequiredUser
from app.db import SessionDep
from app.models import Category, CollectionEntry, Work
from app.netflix import NetflixFormatError, import_netflix, parse_viewing_history
from app.services import tmdb
from app.templating import flash, render

router = APIRouter(prefix="/me")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
BACK = "/me/collection#film"


@router.post("/netflix/import")
async def netflix_import(request: Request, session: SessionDep, me: RequiredUser, history: UploadFile | None = File(None)):
    if history is None or not history.filename:
        flash(request, "請選擇 Netflix 的觀看紀錄檔（NetflixViewingHistory.csv）")
        return RedirectResponse(BACK, status_code=303)
    if not tmdb.configured():
        flash(request, "伺服器尚未設定 TMDB_API_KEY，暫時無法比對片名")
        return RedirectResponse(BACK, status_code=303)
    data = await history.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        flash(request, "檔案太大了（上限 20 MB）")
        return RedirectResponse(BACK, status_code=303)
    try:
        titles = parse_viewing_history(data)
    except NetflixFormatError:
        flash(request, "讀不懂這個檔案，請上傳 Netflix「觀看記錄」下載的 NetflixViewingHistory.csv")
        return RedirectResponse(BACK, status_code=303)
    try:
        result = await import_netflix(session, me, titles)
    except tmdb.TmdbError:
        flash(request, "TMDB 暫時無法使用，請稍後再試")
        return RedirectResponse(BACK, status_code=303)

    msg = f"比對到 {result.matched} 部作品"
    if result.unmatched:
        msg += f"，{len(result.unmatched)} 部找不到（例如《{result.unmatched[0]}》）"
    if result.skipped:
        msg += f"，另有 {result.skipped} 部看比較少的沒有匯入"
    if result.new_anime:
        msg += f"，其中 {result.new_anime} 部日本動畫放進「動畫」類別"
    if result.new:
        flash(request, f"{msg}。新增 {result.new} 部，確認後才會公開")
        first = "film" if result.new > result.new_anime else "anime"
        return RedirectResponse(f"/me/review/{first}", status_code=303)
    flash(request, f"{msg}，沒有新的作品")
    return RedirectResponse(BACK, status_code=303)


def _pending(session: SessionDep, me, category: Category):
    return session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == me.id, Work.category == category, col(CollectionEntry.pending_review).is_(True))
        .order_by(col(CollectionEntry.play_count).desc().nulls_last())
    ).all()


@router.get("/review/{kind}", response_class=HTMLResponse)
def review(request: Request, session: SessionDep, me: RequiredUser, kind: str):
    category = next((c for c in Category if c.value == kind), None)
    if category is None:
        raise HTTPException(status_code=404)
    rows = _pending(session, me, category)
    if not rows:
        return RedirectResponse(f"/me/collection#{kind}", status_code=303)
    return render(request, "pending_review.html", me=me, rows=rows, category=category)


@router.post("/review/{kind}")
async def submit_review(request: Request, session: SessionDep, me: RequiredUser, kind: str):
    category = next((c for c in Category if c.value == kind), None)
    if category is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    publish = {int(v) for v in form.getlist("publish") if str(v).isdigit()}
    shown = 0
    for entry, _ in _pending(session, me, category):
        entry.pending_review = False
        entry.hidden = entry.id not in publish
        shown += not entry.hidden
        session.add(entry)
    session.commit()
    flash(request, f"已公開 {shown} 部，其餘設為隱藏，之後可在收藏中調整")
    if category == Category.film and _pending(session, me, Category.anime):
        return RedirectResponse("/me/review/anime", status_code=303)  # the anime from the same import
    return RedirectResponse(f"/me/collection#{kind}", status_code=303)
