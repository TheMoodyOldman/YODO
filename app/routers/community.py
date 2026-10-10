"""Public work pages (大家的評價、短評、留言區) and the 討論區 sticky-note board."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, col, select

from app import community
from app.anime import TIERED
from app.auth import CurrentUser, RequiredUser
from app.db import SessionDep
from app.models import Category, CollectionEntry, Post, PostReply, Review, ReviewLike, User, Work, WorkComment, utcnow
from app.routers.match import is_admin
from app.routers.me import _add_to_collection
from app.routers.work import CATEGORY_COLORS
from app.templating import flash, render
from app.workinfo import get_work_info

router = APIRouter()

NOTES_PER_PAGE = 30


def _work(session: Session, work_id: int) -> Work:
    work = session.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404)
    return work


def _clean(text: str, limit: int) -> str | None:
    text = text.strip()
    return text if text and len(text) <= limit else None


# ---------- public work page ----------


@router.get("/w/{work_id}", response_class=HTMLResponse)
async def work_public(request: Request, session: SessionDep, me: CurrentUser, work_id: int, sort: str = ""):
    work = session.get(Work, work_id)
    if work is None:
        return render(request, "not_found.html", status_code=404, me=me)
    reviews = community.reviews_for(session, work, me, newest=sort == "new")
    my_entry = session.exec(
        select(CollectionEntry).where(CollectionEntry.user_id == me.id, CollectionEntry.work_id == work.id)
    ).first() if me else None
    my_review = next((v.review for v in reviews if me and v.author.id == me.id), None)
    info = await get_work_info(work)
    return render(
        request,
        "work_public.html",
        me=me,
        work=work,
        info=info,
        stats=community.work_stats(session, work),
        reviews=reviews,
        my_review=my_review,
        my_entry=my_entry,
        comments=community.comments_for(session, work, me),
        sort="new" if sort == "new" else "",
        can_add=work.category in TIERED,
        admin=is_admin(me),
        color=info.color or CATEGORY_COLORS[work.category],
        cover=info.image or work.cover_url,
        MAX_REVIEW=community.MAX_REVIEW,
        MAX_COMMENT=community.MAX_COMMENT,
    )


@router.post("/w/{work_id}/add")
def add_from_public(request: Request, session: SessionDep, me: RequiredUser, work_id: int):
    """Add a rated-category work straight from its public page, then rate it in the collection."""
    work = _work(session, work_id)
    if work.category not in TIERED:
        raise HTTPException(status_code=400)
    return _add_to_collection(request, session, me, work, "")


@router.post("/w/{work_id}/review")
def save_review(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    work_id: int,
    body: Annotated[str, Form()] = "",
    spoiler: Annotated[bool, Form()] = False,
):
    work = _work(session, work_id)
    back = f"/w/{work.id}#reviews"
    text = _clean(body, community.MAX_REVIEW)
    if text is None:
        flash(request, f"短評請寫 1–{community.MAX_REVIEW} 字")
        return RedirectResponse(back, status_code=303)
    review = session.exec(select(Review).where(Review.user_id == me.id, Review.work_id == work.id)).first()
    if review is None:
        review = Review(user_id=me.id, work_id=work.id, body=text)
    review.body, review.spoiler, review.updated_at = text, spoiler, utcnow()
    session.add(review)
    session.commit()
    flash(request, "已發布短評")
    return RedirectResponse(back, status_code=303)


@router.post("/reviews/{review_id}/delete")
def delete_review(request: Request, session: SessionDep, me: RequiredUser, review_id: int):
    review = session.get(Review, review_id)
    if review is None or (review.user_id != me.id and not is_admin(me)):
        raise HTTPException(status_code=404)
    for like in session.exec(select(ReviewLike).where(ReviewLike.review_id == review.id)):
        session.delete(like)
    session.delete(review)
    session.commit()
    flash(request, "已刪除短評")
    return RedirectResponse(f"/w/{review.work_id}#reviews", status_code=303)


@router.post("/reviews/{review_id}/like")
def like_review(request: Request, session: SessionDep, me: RequiredUser, review_id: int):
    review = session.get(Review, review_id)
    if review is None or review.user_id in community.hidden_authors(session, me):
        raise HTTPException(status_code=404)
    like = session.exec(select(ReviewLike).where(ReviewLike.review_id == review.id, ReviewLike.user_id == me.id)).first()
    if like:
        session.delete(like)
    elif review.user_id != me.id:  # no liking your own review
        session.add(ReviewLike(review_id=review.id, user_id=me.id))
    session.commit()
    count = len(session.exec(select(ReviewLike.id).where(ReviewLike.review_id == review.id)).all())
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"likes": count, "liked": like is None and review.user_id != me.id})
    return RedirectResponse(f"/w/{review.work_id}#review-{review.id}", status_code=303)


@router.post("/w/{work_id}/comments")
def add_work_comment(request: Request, session: SessionDep, me: RequiredUser, work_id: int, body: Annotated[str, Form()] = ""):
    work = _work(session, work_id)
    text = _clean(body, community.MAX_COMMENT)
    if text is None:
        flash(request, f"留言請寫 1–{community.MAX_COMMENT} 字")
    else:
        session.add(WorkComment(work_id=work.id, user_id=me.id, body=text))
        session.commit()
    return RedirectResponse(f"/w/{work.id}#comments", status_code=303)


@router.post("/work-comments/{comment_id}/delete")
def delete_work_comment(session: SessionDep, me: RequiredUser, comment_id: int):
    comment = session.get(WorkComment, comment_id)
    if comment is None or (comment.user_id != me.id and not is_admin(me)):
        raise HTTPException(status_code=404)
    session.delete(comment)
    session.commit()
    return RedirectResponse(f"/w/{comment.work_id}#comments", status_code=303)


# ---------- 討論區 ----------


def _category(value: str) -> Category | None:
    return next((c for c in Category if c.value == value), None)


@router.get("/discuss", response_class=HTMLResponse)
def discuss(request: Request, session: SessionDep, me: CurrentUser, c: str = "", page: int = 0):
    category = _category(c)
    page = max(page, 0)
    rows = community.notes(session, me, category, NOTES_PER_PAGE + 1, page * NOTES_PER_PAGE)
    return render(
        request,
        "discuss.html",
        me=me,
        category=category,
        notes=rows[:NOTES_PER_PAGE],
        page=page,
        has_more=len(rows) > NOTES_PER_PAGE,
        NOTE_COLORS=community.NOTE_COLORS,
        MAX_NOTE=community.MAX_NOTE,
        NOTE_DAYS=community.NOTE_DAYS,
    )


@router.post("/discuss")
def new_note(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    category: Annotated[str, Form()] = "",
    body: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "yellow",
    spoiler: Annotated[bool, Form()] = False,
):
    cat = _category(category)
    text = _clean(body, community.MAX_NOTE)
    back = "/discuss" + (f"?c={cat.value}" if cat else "")
    if cat is None:
        flash(request, "請選擇分類")
        return RedirectResponse(back, status_code=303)
    if text is None:
        flash(request, f"便利貼請寫 1–{community.MAX_NOTE} 字")
        return RedirectResponse(back, status_code=303)
    post = Post(user_id=me.id, category=cat, body=text, spoiler=spoiler,
                color=color if color in community.NOTE_COLOR_KEYS else "yellow")
    session.add(post)
    session.commit()
    return RedirectResponse(f"/discuss/{post.id}", status_code=303)


def _visible_post(session: Session, me: User | None, post_id: int) -> tuple[Post, User]:
    post = session.get(Post, post_id)
    author = session.get(User, post.user_id) if post else None
    if post is None or author is None or author.id in community.hidden_authors(session, me):
        raise HTTPException(status_code=404)
    return post, author


@router.get("/discuss/{post_id}", response_class=HTMLResponse)
def thread(request: Request, session: SessionDep, me: CurrentUser, post_id: int):
    try:
        post, author = _visible_post(session, me, post_id)
    except HTTPException:
        return render(request, "not_found.html", status_code=404, me=me)
    return render(
        request,
        "discuss_thread.html",
        me=me,
        post=post,
        author=author,
        replies=community.replies_for(session, post, me),
        expired=community.note_expired(post),
        NOTE_DAYS=community.NOTE_DAYS,
        admin=is_admin(me),
        MAX_COMMENT=community.MAX_COMMENT,
    )


@router.post("/discuss/{post_id}/replies")
def reply(request: Request, session: SessionDep, me: RequiredUser, post_id: int, body: Annotated[str, Form()] = ""):
    post, _ = _visible_post(session, me, post_id)
    text = _clean(body, community.MAX_COMMENT)
    if text is None:
        flash(request, f"回覆請寫 1–{community.MAX_COMMENT} 字")
        return RedirectResponse(f"/discuss/{post.id}", status_code=303)
    session.add(PostReply(post_id=post.id, user_id=me.id, body=text))
    post.reply_count += 1
    post.last_activity_at = utcnow()
    session.add(post)
    session.commit()
    return RedirectResponse(f"/discuss/{post.id}#replies", status_code=303)


@router.post("/discuss/{post_id}/delete")
def delete_note(request: Request, session: SessionDep, me: RequiredUser, post_id: int):
    post = session.get(Post, post_id)
    if post is None or (post.user_id != me.id and not is_admin(me)):
        raise HTTPException(status_code=404)
    for r in session.exec(select(PostReply).where(PostReply.post_id == post.id)):
        session.delete(r)
    session.delete(post)
    session.commit()
    flash(request, "已刪除便利貼")
    return RedirectResponse(f"/discuss?c={post.category.value}", status_code=303)


@router.post("/discuss/replies/{reply_id}/delete")
def delete_reply(session: SessionDep, me: RequiredUser, reply_id: int):
    r = session.get(PostReply, reply_id)
    post = session.get(Post, r.post_id) if r else None
    if r is None or post is None or me.id not in (r.user_id, post.user_id) and not is_admin(me):
        raise HTTPException(status_code=404)
    session.delete(r)
    post.reply_count = max(0, post.reply_count - 1)
    session.add(post)
    session.commit()
    return RedirectResponse(f"/discuss/{post.id}#replies", status_code=303)

