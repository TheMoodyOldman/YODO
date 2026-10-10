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
from app.anime import TIERED, parse_status, parse_tag, parse_tier, status_rank, tier_rank
from app.matching import LOOKING_FOR, REGIONS, looking_keys
from app.music import LASTFM, YOUTUBE
from app.privacy import get_privacy, set_privacy
from app.services import anilist, books, steam, tmdb
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
    Category.film: "還沒有影視作品。搜尋電影、影集，或匯入 Netflix 觀看紀錄。",
    Category.book: "還沒有書。搜尋書名或作者加入。",
}
# Search box query parameter per category on the collection page.
SEARCH_PARAMS = {Category.anime: "q", Category.film: "fq", Category.book: "bq"}


def _search_url(category: Category, query: str = "", **extra: str) -> str:
    params = ({SEARCH_PARAMS[category]: query} if query else {}) | extra
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"/me/collection{'?' + qs if qs else ''}#{category.value}"


def _owned_entry(session: Session, user: User, entry_id: int) -> CollectionEntry:
    entry = session.get(CollectionEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404)
    return entry


def _sort_key(category: Category):
    if category == Category.game:
        return lambda r: (r[0].playtime_minutes or 0, r[0].added_at)
    if category == Category.music:
        return lambda r: (r[0].play_count or 0, r[0].added_at)
    if category == Category.book:
        return lambda r: (status_rank(r[0].status), tier_rank(r[0].tier), r[0].added_at)
    return lambda r: (tier_rank(r[0].tier), r[0].play_count or 0, r[0].added_at)


@router.get("/collection", response_class=HTMLResponse)
async def collection(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    q: str = "",
    fq: str = "",
    bq: str = "",
    music: str = "",
    rate: int | None = None,
):
    q, fq, bq = q.strip(), fq.strip(), bq.strip()
    searches: dict[Category, dict] = {
        c: {"query": v, "results": [], "error": None}
        for c, v in ((Category.anime, q), (Category.film, fq), (Category.book, bq))
    }
    if q:
        try:
            searches[Category.anime]["results"] = await anilist.search_anime(q)
        except anilist.AniListError:
            searches[Category.anime]["error"] = "AniList 暫時無法連線，請稍後再試"
    if fq:
        try:
            searches[Category.film]["results"] = await tmdb.search(fq)
        except tmdb.TmdbError:
            searches[Category.film]["error"] = "TMDB 暫時無法使用" + ("" if tmdb.configured() else "（伺服器尚未設定 TMDB_API_KEY）")
    if bq:
        try:
            searches[Category.book]["results"] = await books.search(bq)
        except books.BooksError:
            searches[Category.book]["error"] = "書籍資料庫暫時無法連線，請稍後再試"

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
    owned = {(work.source, work.external_id) for _, work in rows}

    for category in Category:
        by_category[category].sort(key=_sort_key(category), reverse=True)
    # Music libraries can hold thousands of songs: list the most played first, capped unless asked.
    # Not deduped across sources (unlike the profile rankings): every imported copy stays manageable.
    music_total = len(by_category[Category.music])
    if music != "all":
        by_category[Category.music] = by_category[Category.music][:MUSIC_LIST_LIMIT]
    sources = {work.source for _, work in rows}
    counts = {c: len(by_category[c]) for c in Category} | {Category.music: music_total}

    # Tab shown when the URL has no #hash (redirects after form posts add one).
    searched = next((c for c, srch in searches.items() if srch["query"]), None)
    if searched:
        default_tab = searched
    elif music == "all":
        default_tab = Category.music
    else:
        default_tab = next((c for c in Category if counts[c]), Category.game)

    # Just added something rateable: open its rating dialog.
    rate_entry = next(((e, w) for c in TIERED for e, w in by_category[c] if e.id == rate), None)
    rate_next = (
        _search_url(rate_entry[1].category, searches[rate_entry[1].category]["query"]) if rate_entry else "/me/collection"
    )

    return render(
        request,
        "collection.html",
        me=me,
        q=q,
        searches=searches,
        owned=owned,
        by_category=by_category,
        pending=pending,
        counts=counts,
        default_tab=default_tab,
        music_total=music_total,
        PAGE_ITEMS=PAGE_ITEMS,
        EMPTY_HINTS=EMPTY_HINTS,
        has_youtube=YOUTUBE in sources,
        has_lastfm=LASTFM in sources,
        has_netflix=any(e.play_count for e, _ in by_category[Category.film]),
        tmdb_ready=tmdb.configured(),
        books_source=books.active_source(),
        steam_profile_url=steam.profile_url(me.steam_id) if me.steam_id else None,
        rate_entry=rate_entry,
        rate_next=rate_next,
    )


def _add_to_collection(request: Request, session: Session, me: User, work: Work, query: str) -> RedirectResponse:
    """Add a searched work, then reopen the collection with its rating dialog."""
    exists = session.exec(
        select(CollectionEntry).where(CollectionEntry.user_id == me.id, CollectionEntry.work_id == work.id)
    ).first()
    if exists is not None:
        session.commit()
        return RedirectResponse(_search_url(work.category, query), status_code=303)
    entry = CollectionEntry(user_id=me.id, work_id=work.id)
    session.add(entry)
    record(session, me.id, ActivityKind.anime_added, work.id)  # the "added" activity, for any rated category
    session.commit()
    flash(request, f"已加入《{work.title}》")
    return RedirectResponse(_search_url(work.category, query, rate=str(entry.id)), status_code=303)


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
        return RedirectResponse(_search_url(Category.anime, q), status_code=303)
    if anime is None:
        raise HTTPException(status_code=404)
    work = upsert_work(
        session, category=Category.anime, source="anilist", external_id=str(anime.id), title=anime.title,
        original_title=anime.original_title, cover_url=anime.cover_url, year=anime.year,
    )
    return _add_to_collection(request, session, me, work, q)


@router.post("/collection/film")
async def add_film(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    tmdb_id: Annotated[str, Form()],
    fq: Annotated[str, Form()] = "",
):
    try:
        title = await tmdb.get_title(tmdb_id)
    except tmdb.TmdbError:
        flash(request, "TMDB 暫時無法使用，請稍後再試")
        return RedirectResponse(_search_url(Category.film, fq), status_code=303)
    if title is None:
        raise HTTPException(status_code=404)
    work = upsert_work(
        session, category=Category.film, source="tmdb", external_id=title.external_id, title=title.title,
        original_title=title.original_title, cover_url=title.cover_url, year=title.year,
    )
    return _add_to_collection(request, session, me, work, fq)


@router.post("/collection/book")
async def add_book(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    source: Annotated[str, Form()],
    book_id: Annotated[str, Form()],
    bq: Annotated[str, Form()] = "",
):
    if source not in (books.GOOGLE, books.OPENLIBRARY):
        raise HTTPException(status_code=400)
    try:
        book = await books.get_book(source, book_id)
    except books.BooksError:
        flash(request, "書籍資料庫暫時無法連線，請稍後再試")
        return RedirectResponse(_search_url(Category.book, bq), status_code=303)
    if book is None:
        raise HTTPException(status_code=404)
    work = upsert_work(
        session, category=Category.book, source=book.source, external_id=book.external_id, title=book.title,
        creator=book.authors or None, cover_url=book.cover_url, year=book.year,
    )
    return _add_to_collection(request, session, me, work, bq)


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
    status: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    """Tier + tag (+ reading status for books). Plain form posts redirect back; fetch() autosaves get 204."""
    entry = _owned_entry(session, me, entry_id)
    category = session.get(Work, entry.work_id).category
    if category not in TIERED:
        raise HTTPException(status_code=400)
    entry.tier, entry.tag = parse_tier(tier), parse_tag(tag, category)
    if category == Category.book:
        entry.status = parse_status(status)
    session.add(entry)
    # Rated the day it was added: the "added" item already shows the verdict, so just bump it.
    if entry.tier or entry.tag or entry.status:
        added_today = has_today(session, me.id, ActivityKind.anime_added, entry.work_id)
        record(session, me.id, ActivityKind.anime_added if added_today else ActivityKind.anime_rated, entry.work_id)
    session.commit()
    if request.headers.get("x-requested-with") == "fetch":
        return Response(status_code=204)
    flash(request, "已儲存評價")
    return RedirectResponse(safe_next(next, f"/me/collection#{category.value}"), status_code=303)


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
    return render(
        request,
        "settings.html",
        me=me,
        privacy=get_privacy(session, me.id),
        REGIONS=REGIONS,
        LOOKING_FOR=LOOKING_FOR,
        my_looking=looking_keys(me),
    )


@router.post("/settings")
async def save_settings(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    me.display_name = str(form.get("display_name", "")).strip()[:MAX_DISPLAY_NAME] or me.username
    me.bio = str(form.get("bio", "")).strip()[:MAX_BIO]
    region = str(form.get("region", ""))
    me.region = region if region in REGIONS else None
    me.looking_for = ",".join(k for k, _ in LOOKING_FOR if k in form.getlist("looking_for")) or None
    me.hide_from_match = form.get("show_in_match") != "1"
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
