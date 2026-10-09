from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import col, select

from app.auth import RequiredUser
from app.db import SessionDep
from app.models import Category, CollectionEntry, User, Work
from app.music import top_artists, top_songs
from app.templating import flash, render

router = APIRouter(prefix="/me/music")

BACK = "/me/collection#music"


def _pending_music(session: SessionDep, me: User) -> list[tuple[CollectionEntry, Work]]:
    return list(
        session.exec(
            select(CollectionEntry, Work)
            .join(Work, col(Work.id) == CollectionEntry.work_id)
            .where(
                CollectionEntry.user_id == me.id,
                Work.category == Category.music,
                col(CollectionEntry.pending_review).is_(True),
            )
        ).all()
    )


@router.get("/review", response_class=HTMLResponse)
def review(request: Request, session: SessionDep, me: RequiredUser):
    rows = _pending_music(session, me)
    if not rows:
        return RedirectResponse(BACK, status_code=303)
    return render(
        request,
        "music_review.html",
        me=me,
        total=len(rows),
        artists=top_artists(rows, 15),
        songs=top_songs(rows, 20),
    )


@router.post("/review")
async def submit_review(request: Request, session: SessionDep, me: RequiredUser):
    form = await request.form()
    # Only items that were listed on the page can be hidden; unchecked = listed - checked.
    hide_artists = set(map(str, form.getlist("listed_artist"))) - set(map(str, form.getlist("artist")))
    hide_songs = set(map(str, form.getlist("listed_song"))) - set(map(str, form.getlist("song")))
    hidden = 0
    for entry, work in _pending_music(session, me):
        entry.pending_review = False
        if str(entry.id) in hide_songs or (work.creator and work.creator.casefold() in hide_artists):
            entry.hidden = True
            hidden += 1
        session.add(entry)
    session.commit()
    flash(request, f"音樂收藏已公開，隱藏了 {hidden} 首歌" if hidden else "音樂收藏已公開")
    return RedirectResponse(BACK, status_code=303)
