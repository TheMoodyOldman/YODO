from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.auth import RequiredUser
from app.card_render import fetch_images, image_urls, render_card
from app.cards import Period, available_periods, recap_stats
from app.db import SessionDep
from app.models import CardEvent, Category, Visibility
from app.privacy import get_privacy
from app.templating import render

router = APIRouter(prefix="/me/card")

ACTIONS = {"share", "download"}
PERIOD_LABELS = {"month": "當月", "year": "當年", "all": "有史以來"}


def _categories(values: list[str]) -> set[Category]:
    valid = {c.value for c in Category}
    return {Category(v) for v in values if v in valid}


def _pick_period(avail, period: str, month: str, year: str) -> Period:
    """The requested period if it has data, else the closest sensible default."""
    if period == "year" and avail.years:
        return Period("year", year if year in avail.years else avail.years[0])
    if period == "all" or not avail.months:
        return Period("all", "all")
    return Period("month", month if month in avail.months else avail.months[0])


@router.get("", response_class=HTMLResponse)
def card_page(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    period: str = "month",
    month: str = "",
    year: str = "",
    c: list[str] | None = Query(default=None),
):
    avail = available_periods(session, me)
    if not avail.all_time:
        return render(request, "card.html", me=me, avail=avail)

    chosen = _pick_period(avail, period, month, year)
    stats = recap_stats(session, me, chosen)
    privacy = get_privacy(session, me.id)
    options = [cat for cat in Category if stats.has(cat)]
    if c is None:
        # First visit: leave out categories the user keeps private on their profile.
        selected = {cat for cat in options if privacy[cat] != Visibility.private}
    else:
        selected = _categories(c) & set(options)

    image_url = None
    if selected:
        query = urlencode(
            [("period", chosen.kind), ("key", chosen.key), *[("c", cat.value) for cat in Category if cat in selected]]
        )
        image_url = f"/me/card/image.jpg?{query}"

    def period_href(kind: str) -> str:
        return f"/me/card?{urlencode([('period', kind), *[('c', cat.value) for cat in sorted(selected)]])}"

    return render(
        request,
        "card.html",
        me=me,
        avail=avail,
        period=chosen,
        stats=stats,
        options=options,
        selected=selected,
        privacy=privacy,
        image_url=image_url,
        has_steam=bool(me.steam_id),
        PERIOD_NOUN={"month": "這個月", "year": "這一年"},
        period_tabs=[(kind, label, period_href(kind)) for kind, label in PERIOD_LABELS.items()
                     if kind == "all" or (avail.months if kind == "month" else avail.years)],
    )


@router.get("/image.jpg")
async def card_image(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    period: str = "month",
    key: str = "",
    c: list[str] = Query(default=[]),
):
    chosen = Period.parse(period, key)
    if chosen is None:
        raise HTTPException(status_code=404)
    stats = recap_stats(session, me, chosen)
    categories = {cat for cat in _categories(c) if stats.has(cat)}
    if not categories:
        raise HTTPException(status_code=404)

    images = await fetch_images(image_urls(stats, categories))
    footer = f"{request.url.netloc}/u/{me.username}"
    data = await run_in_threadpool(render_card, stats, me.display_name, footer, categories, images)
    return Response(
        data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="yodo-recap-{chosen.key}.jpg"',
        },
    )


class CardEventIn(BaseModel):
    period: str
    key: str
    action: str


@router.post("/events", status_code=204)
def card_event(event: CardEventIn, session: SessionDep, me: RequiredUser):
    chosen = Period.parse(event.period, event.key)
    if event.action not in ACTIONS or chosen is None:
        raise HTTPException(status_code=422)
    session.add(CardEvent(user_id=me.id, period=chosen.kind, month=chosen.key, action=event.action))
    session.commit()
    return Response(status_code=204)
