from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlmodel import col, select

from app.auth import CurrentUser, is_locked
from app.db import SessionDep
from app.models import Category, CollectionEntry, User, Work
from app.anime import TIERS, tier_rank
from app.genres import user_style
from app.matching import LOOKING_LABELS, looking_keys
from app.music import top_artists, top_songs
from app.privacy import can_view, get_privacy
from app.social import Relation, relation
from app.templating import render

router = APIRouter()

TOP_N = 10
OVERVIEW_ITEMS = 8  # cards per category in the overview tab's scrolling row
PAGE_ITEMS = 24  # cards per "顯示更多" step in a category tab


@router.get("/u/{username}", response_class=HTMLResponse)
def profile(request: Request, username: str, session: SessionDep, me: CurrentUser):
    owner = session.exec(select(User).where(User.username == username.lower())).first()
    rel = relation(session, me, owner) if owner else None
    if owner is None or rel == Relation.blocked or is_locked(owner):
        return render(request, "not_found.html", status_code=404, me=me)

    privacy = get_privacy(session, owner.id)
    sections = []
    for category in Category:
        if not can_view(privacy[category], owner, me, is_friend=rel == Relation.friends):
            continue
        rows = session.exec(
            select(CollectionEntry, Work)
            .join(Work, col(Work.id) == CollectionEntry.work_id)
            .where(
                CollectionEntry.user_id == owner.id,
                Work.category == category,
                col(CollectionEntry.hidden).is_(False),
                col(CollectionEntry.pending_review).is_(False),
            )
            .order_by(
                col(CollectionEntry.playtime_minutes).desc().nulls_last(),
                col(CollectionEntry.play_count).desc().nulls_last(),
                col(CollectionEntry.added_at).desc(),
            )
        ).all()
        if category == Category.anime:
            rows = sorted(rows, key=lambda r: tier_rank(r[0].tier), reverse=True)  # stable: keeps added order per tier
        section = {"category": category, "visibility": privacy[category], "items": rows}
        if category == Category.anime:
            section["tier_groups"] = [
                (label, [r for r in rows if r[0].tier == tier]) for tier, label in TIERS
            ] + [("未評價", [r for r in rows if not r[0].tier])]
        if category == Category.music:
            section["top_artists"] = top_artists(list(rows), TOP_N)
            section["top_songs"] = top_songs(list(rows), TOP_N)
        sections.append(section)

    is_owner = me is not None and me.id == owner.id
    return render(
        request,
        "profile.html",
        me=me,
        owner=owner,
        is_owner=is_owner,
        # Owners also get tabs for empty categories, so they see what's missing.
        shown=[s for s in sections if s["items"] or is_owner],
        has_items=any(s["items"] for s in sections),
        OVERVIEW_ITEMS=OVERVIEW_ITEMS,
        PAGE_ITEMS=PAGE_ITEMS,
        page_url=str(request.url),
        relation=rel,
        styles=user_style(session, owner, {s["category"] for s in sections if s["items"]}),
        owner_looking=[LOOKING_LABELS[k] for k in looking_keys(owner)],
    )
