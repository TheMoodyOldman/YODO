from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, col, select

from app.auth import RequiredUser, safe_next
from app.config import settings
from app.db import SessionDep
from app.matching import MIN_ENTRIES, empty_reason, find_matches, looking_keys
from app.models import Block, MatchDismiss, Report, User, utcnow
from app.social import Relation, get_friendship
from app.templating import flash, render

router = APIRouter()

REPORT_REASONS = [
    ("harassment", "騷擾或不當言論"),
    ("impersonation", "冒充他人"),
    ("inappropriate", "不實或不當的內容"),
    ("underage", "疑似未滿 18 歲"),
    ("other", "其他"),
]
REPORT_LABELS = dict(REPORT_REASONS)
MAX_DETAIL = 500


def _target(session: Session, me: User, username: str) -> User:
    user = session.exec(select(User).where(User.username == username.lower())).first()
    if user is None or user.id == me.id:
        raise HTTPException(status_code=404)
    return user


def is_admin(user: User | None) -> bool:
    admins = {u.strip().lower() for u in settings.admin_usernames.split(",") if u.strip()}
    return user is not None and user.username in admins


@router.get("/match", response_class=HTMLResponse)
def match_page(request: Request, session: SessionDep, me: RequiredUser):
    matches = find_matches(session, me)
    return render(
        request,
        "match.html",
        me=me,
        matches=matches,
        empty=None if matches else empty_reason(session, me),
        needs_profile=not me.region and not looking_keys(me),
        MIN_ENTRIES=MIN_ENTRIES,
        Relation=Relation,
    )


@router.post("/match/{username}/dismiss")
def dismiss(request: Request, session: SessionDep, me: RequiredUser, username: str):
    target = _target(session, me, username)
    exists = session.exec(
        select(MatchDismiss).where(MatchDismiss.user_id == me.id, MatchDismiss.dismissed_id == target.id)
    ).first()
    if exists is None:
        session.add(MatchDismiss(user_id=me.id, dismissed_id=target.id))
        session.commit()
    flash(request, f"不會再推薦 {target.display_name} 給你")
    return RedirectResponse("/match", status_code=303)


@router.get("/report/{username}", response_class=HTMLResponse)
def report_form(request: Request, session: SessionDep, me: RequiredUser, username: str, next: str = "", about: str = ""):
    target = _target(session, me, username)
    return render(request, "report.html", me=me, target=target, reasons=REPORT_REASONS, next=next, about=about[:80],
                  MAX_DETAIL=MAX_DETAIL)


@router.post("/report/{username}")
def report_submit(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    username: str,
    reason: Annotated[str, Form()] = "",
    detail: Annotated[str, Form()] = "",
    also_block: Annotated[bool, Form()] = False,
    next: Annotated[str, Form()] = "",
    about: Annotated[str, Form()] = "",
):
    target = _target(session, me, username)
    if reason not in REPORT_LABELS:
        flash(request, "請選擇檢舉原因")
        return RedirectResponse(f"/report/{target.username}", status_code=303)
    detail = detail.strip()[:MAX_DETAIL]
    if about.strip():  # a specific post, e.g. "短評 #12 /w/34"
        detail = f"[{about.strip()[:80]}] {detail}".strip()
    session.add(Report(reporter_id=me.id, reported_id=target.id, reason=reason, detail=detail))
    if also_block:
        if f := get_friendship(session, me.id, target.id):
            session.delete(f)
        if not session.exec(select(Block).where(Block.blocker_id == me.id, Block.blocked_id == target.id)).first():
            session.add(Block(blocker_id=me.id, blocked_id=target.id))
    session.commit()
    flash(request, "已收到檢舉，我們會盡快處理。" + ("也已封鎖對方。" if also_block else ""))
    return RedirectResponse(safe_next(next, "/match") if not also_block else "/match", status_code=303)


@router.get("/admin/reports", response_class=HTMLResponse)
def admin_reports(request: Request, session: SessionDep, me: RequiredUser, show: str = "open"):
    if not is_admin(me):
        raise HTTPException(status_code=404)
    query = select(Report).order_by(col(Report.created_at).desc())
    if show != "all":
        query = query.where(col(Report.resolved).is_(None))
    reports = session.exec(query).all()
    ids = {r.reporter_id for r in reports} | {r.reported_id for r in reports}
    users = {u.id: u for u in session.exec(select(User).where(col(User.id).in_(ids)))}
    return render(
        request, "admin_reports.html", me=me, reports=reports, users=users, labels=REPORT_LABELS, show=show
    )


@router.post("/admin/reports/{report_id}/resolve")
def resolve_report(session: SessionDep, me: RequiredUser, report_id: int):
    if not is_admin(me):
        raise HTTPException(status_code=404)
    report = session.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404)
    report.resolved = True
    session.add(report)
    session.commit()
    return RedirectResponse("/admin/reports", status_code=303)
