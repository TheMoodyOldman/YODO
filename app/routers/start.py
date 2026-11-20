"""新手教學 cover picker: /me/start (tabs of popular covers to tick, with search) and its save."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import quickpick
from app.auth import RequiredUser, safe_next
from app.db import SessionDep
from app.models import Category
from app.services.popular_sources import PopularError
from app.templating import flash, render

router = APIRouter(prefix="/me/start")

TAB_LABELS = {Category.anime: "動畫", Category.game: "遊戲", Category.music: "音樂", Category.book: "書籍", Category.film: "影視"}
UNITS = {Category.anime: "部", Category.game: "款", Category.music: "位", Category.book: "本", Category.film: "部"}
SEARCH_HINTS = {Category.anime: "搜尋動畫（中文、日文、英文都可以）", Category.game: "搜尋 Steam 遊戲", Category.music: "搜尋歌手",
                Category.book: "搜尋書名或作者", Category.film: "搜尋電影或影集"}


@router.get("", response_class=HTMLResponse)
async def start_page(request: Request, session: SessionDep, me: RequiredUser, next: str = ""):
    have = quickpick.entry_keys(session, me)
    tabs = []
    for cat in quickpick.CATEGORIES:
        items = await quickpick.popular(session, cat)
        tabs.append({
            "cat": cat, "label": TAB_LABELS[cat], "unit": UNITS[cat], "hint": SEARCH_HINTS[cat],
            "square": cat == Category.music,
            "items": [(i, have.get(i.key)) for i in items],
        })
    picked = sum(1 for e in have.values() if e.quick_pick)
    return render(request, "start.html", me=me, tabs=tabs, picked=picked, next=safe_next(next, f"/u/{me.username}"))


@router.get("/search")
async def search(session: SessionDep, me: RequiredUser, cat: str = "", q: str = ""):
    try:
        category = Category(cat)
    except ValueError:
        return JSONResponse({"items": [], "error": "未知的分類"}, status_code=400)
    try:
        items = await quickpick.search(session, category, q)
    except PopularError:
        return JSONResponse({"items": [], "error": "搜尋暫時無法使用（需要網路），可以先從上面的熱門清單勾選"})
    from app.local_assets import url_for

    return {"items": [{"key": i.key, "title": i.title, "sub": i.sub or (str(i.year) if i.year else ""),
                       "cover": url_for(i.cover_url)} for i in items]}


@router.post("")
async def save(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    result = await quickpick.save(session, me, [str(v) for v in form.getlist("pick")], [str(v) for v in form.getlist("shown")])
    parts = [f"加入 {result.added} 個收藏"] if result.added else []
    if result.removed:
        parts.append(f"移除 {result.removed} 個")
    if result.skipped:
        parts.append(f"{result.skipped} 個暫時找不到資料，沒有加入")
    flash(request, "、".join(parts) if parts else "沒有變更")
    return RedirectResponse(safe_next(str(form.get("next") or ""), f"/u/{me.username}"), status_code=303)
