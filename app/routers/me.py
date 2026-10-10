from collections import Counter
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session, col, select

from app.auth import RequiredUser, safe_next
from app.db import SessionDep
from app.activity import has_today, record
from app.models import ActivityKind, Category, CollectionEntry, User, Visibility, Work
from app.anime import parse_tag, parse_tier, tier_rank
from app.music import LASTFM, YOUTUBE
from app.privacy import get_privacy, set_privacy
from app.services import anilist, steam
from app.templating import flash, render
from app.works import upsert_work

router = APIRouter(prefix="/me")

MAX_DISPLAY_NAME = 30
MAX_BIO = 200
MUSIC_LIST_LIMIT = 50
PAGE_ITEMS = 24  # rows per "顯示更多" step
EMPTY_HINTS = {
    Category.game: "還沒有遊戲。連結 Steam 就能匯入遊戲庫。",
    Category.anime: "還沒有動畫。用上面的搜尋加入喜歡的作品。",
    Category.music: "還沒有音樂。連結 Last.fm 或上傳 YouTube 紀錄來匯入。",
}


def _collection_url(q: str = "") -> str:
    return f"/me/collection?q={quote(q)}" if q else "/me/collection#anime"


def _owned_entry(session: Session, user: User, entry_id: int) -> CollectionEntry:
    entry = session.get(CollectionEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404)
    return entry


@router.get("/collection", response_class=HTMLResponse)
async def collection(
    request: Request, session: SessionDep, me: RequiredUser, q: str = "", music: str = "", rate: int | None = None
):
    q = q.strip()
    results: list[anilist.Anime] = []
    search_error = None
    if q:
        try:
            results = await anilist.search_anime(q)
        except anilist.AniListError:
            search_error = "AniList 暫時無法連線，請稍後再試"

    rows = session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == me.id)
        .order_by(col(CollectionEntry.added_at).desc())
    ).all()
    by_category: dict[Category, list] = {c: [] for c in Category}
    pending: Counter[Category] = Counter()
    for entry, work in rows:
        if entry.pending_review:
            pending[work.category] += 1
        else:
            by_category[work.category].append((entry, work))
    owned_anilist_ids = {work.external_id for _, work in rows if work.source == "anilist"}

    # Music libraries can hold thousands of songs: list the most played first, capped unless asked.
    # Not deduped across sources (unlike the profile rankings): every imported copy stays manageable.
    music_rows = sorted(by_category[Category.music], key=lambda r: (r[0].play_count or 0, r[0].added_at), reverse=True)
    music_total = len(music_rows)
    by_category[Category.music] = music_rows if music == "all" else music_rows[:MUSIC_LIST_LIMIT]
    by_category[Category.game].sort(key=lambda r: r[0].playtime_minutes or 0, reverse=True)
    by_category[Category.anime].sort(key=lambda r: tier_rank(r[0].tier), reverse=True)  # stable: newest first per tier
    sources = {work.source for _, work in rows}
    counts = {c: len(by_category[c]) for c in Category} | {Category.music: music_total}

    # Tab shown when the URL has no #hash (redirects after form posts add one).
    if q:
        default_tab = Category.anime
    elif music == "all":
        default_tab = Category.music
    else:
        default_tab = next((c for c in Category if counts[c]), Category.game)

    return render(
        request,
        "collection.html",
        me=me,
        q=q,
        results=results,
        search_error=search_error,
        owned_anilist_ids=owned_anilist_ids,
        by_category=by_category,
        pending=pending,
        counts=counts,
        default_tab=default_tab,
        music_total=music_total,
        PAGE_ITEMS=PAGE_ITEMS,
        EMPTY_HINTS=EMPTY_HINTS,
        has_youtube=YOUTUBE in sources,
        has_lastfm=LASTFM in sources,
        steam_profile_url=steam.profile_url(me.steam_id) if me.steam_id else None,
        # Just added an anime: open the rating dialog for it.
        rate_entry=next((r for r in by_category[Category.anime] if r[0].id == rate), None),
        rate_next=f"/me/collection?q={quote(q)}#anime" if q else "/me/collection#anime",
    )


@router.post("/collection/anime")
async def add_anime(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    anilist_id: Annotated[int, Form()],
    q: Annotated[str, Form()] = "",
):
    try:
        anime = await anilist.get_anime(anilist_id)
    except anilist.AniListError:
        flash(request, "AniList 暫時無法連線，請稍後再試")
        return RedirectResponse(_collection_url(q), status_code=303)
    if anime is None:
        raise HTTPException(status_code=404)

    work = upsert_work(
        session,
        category=Category.anime,
        source="anilist",
        external_id=str(anime.id),
        title=anime.title,
        original_title=anime.original_title,
        cover_url=anime.cover_url,
        year=anime.year,
    )
    exists = session.exec(
        select(CollectionEntry).where(CollectionEntry.user_id == me.id, CollectionEntry.work_id == work.id)
    ).first()
    if exists is not None:
        return RedirectResponse(_collection_url(q), status_code=303)
    entry = CollectionEntry(user_id=me.id, work_id=work.id)
    session.add(entry)
    record(session, me.id, ActivityKind.anime_added, work.id)
    session.commit()
    flash(request, f"已加入《{anime.title}》")
    rate = f"rate={entry.id}"
    return RedirectResponse(f"/me/collection?q={quote(q)}&{rate}#anime" if q else f"/me/collection?{rate}#anime", status_code=303)


@router.post("/collection/{entry_id}")
def update_entry(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    entry_id: int,
    hidden: Annotated[bool, Form()] = False,
):
    entry = _owned_entry(session, me, entry_id)
    entry.hidden = hidden
    session.add(entry)
    session.commit()
    # Songs past the first MUSIC_LIST_LIMIT only render in the "show all" view; return there.
    all_music = "?music=all" if "music=all" in request.headers.get("referer", "") else ""
    return RedirectResponse(f"/me/collection{all_music}#entry-{entry_id}", status_code=303)


@router.post("/collection/{entry_id}/verdict")
def set_verdict(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    entry_id: int,
    tier: Annotated[str, Form()] = "",
    tag: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    """Anime tier + tag. Plain form posts redirect back; fetch() autosaves get 204."""
    entry = _owned_entry(session, me, entry_id)
    if session.get(Work, entry.work_id).category != Category.anime:
        raise HTTPException(status_code=400)
    entry.tier, entry.tag = parse_tier(tier), parse_tag(tag)
    session.add(entry)
    # Rated the day it was added: the "added" item already shows the verdict, so just bump it.
    if entry.tier or entry.tag:
        kind = ActivityKind.anime_added if has_today(session, me.id, ActivityKind.anime_added, entry.work_id) else ActivityKind.anime_rated
        record(session, me.id, kind, entry.work_id)
    session.commit()
    if request.headers.get("x-requested-with") == "fetch":
        return Response(status_code=204)
    flash(request, "已儲存評價")
    return RedirectResponse(safe_next(next, "/me/collection#anime"), status_code=303)


@router.post("/collection/{entry_id}/delete")
def delete_entry(request: Request, session: SessionDep, me: RequiredUser, entry_id: int):
    entry = _owned_entry(session, me, entry_id)
    category = session.get(Work, entry.work_id).category
    session.delete(entry)
    session.commit()
    flash(request, "已從收藏移除")
    return RedirectResponse(f"/me/collection#{category.value}", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
def settings_form(request: Request, session: SessionDep, me: RequiredUser):
    return render(request, "settings.html", me=me, privacy=get_privacy(session, me.id))


@router.post("/settings")
async def save_settings(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    me.display_name = str(form.get("display_name", "")).strip()[:MAX_DISPLAY_NAME] or me.username
    me.bio = str(form.get("bio", "")).strip()[:MAX_BIO]
    session.add(me)
    for category in Category:
        try:
            visibility = Visibility(str(form.get(f"visibility_{category.value}")))
        except ValueError:
            continue
        set_privacy(session, me.id, category, visibility)
    session.commit()
    flash(request, "設定已儲存")
    return RedirectResponse("/me/settings", status_code=303)
