"""電子信箱驗證、更換信箱、忘記密碼。"""

import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import func, select

from app import accounts, mail
from app.auth import CurrentUser, RequiredUser, hash_password
from app.db import SessionDep
from app.models import User
from app.routers.auth import MIN_PASSWORD
from app.templating import flash, render

router = APIRouter()

FORGOT_SENT = "如果這個信箱有註冊並驗證過，我們已經寄出重設密碼的連結，請到信箱收信。"


def _can_resend(request: Request) -> bool:
    return time.time() - request.session.get("verify_sent_at", 0) >= accounts.RESEND_SECONDS


@router.get("/me/verify", response_class=HTMLResponse)
def verify_page(request: Request, me: RequiredUser):
    return render(request, "verify.html", me=me, verified=accounts.is_verified(me), enforced=accounts.enforced(),
                  mail_ready=mail.configured())


@router.post("/me/email")
def change_email(request: Request, tasks: BackgroundTasks, session: SessionDep, me: RequiredUser,
                 email: Annotated[str, Form()] = ""):
    address = accounts.normalize(email)
    if not accounts.valid(address):
        flash(request, "電子信箱格式不正確")
    elif accounts.taken(session, address, except_user=me.id):
        flash(request, "這個電子信箱已經有人使用")
    elif address == me.email:
        flash(request, "這就是你目前的電子信箱")
    else:
        me.email, me.email_verified_at = address, None
        session.add(me)
        session.commit()
        accounts.send_verification(request, tasks, me)
        request.session["verify_sent_at"] = time.time()
        flash(request, f"已更新，驗證信寄到 {address}")
    return RedirectResponse("/me/verify", status_code=303)


@router.post("/me/verify/resend")
def resend(request: Request, tasks: BackgroundTasks, me: RequiredUser):
    if not me.email or accounts.is_verified(me):
        return RedirectResponse("/me/verify", status_code=303)
    if not _can_resend(request):
        flash(request, f"剛剛才寄過，請等 {accounts.RESEND_SECONDS} 秒再試")
    else:
        accounts.send_verification(request, tasks, me)
        request.session["verify_sent_at"] = time.time()
        flash(request, f"驗證信已重新寄到 {me.email}")
    return RedirectResponse("/me/verify", status_code=303)


@router.get("/verify-email")
def verify_email(request: Request, session: SessionDep, me: CurrentUser, token: str = ""):
    user = accounts.verify(session, token)
    if user is None:
        flash(request, "驗證連結無效或已過期，請重新寄一次驗證信")
        return RedirectResponse("/me/verify" if me else "/login", status_code=303)
    flash(request, "電子信箱驗證完成！")
    return RedirectResponse("/me/verify" if me and me.id == user.id else "/login", status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_form(request: Request, me: CurrentUser):
    return render(request, "forgot.html", me=me, mail_ready=mail.configured())


@router.post("/forgot-password")
def forgot(request: Request, tasks: BackgroundTasks, session: SessionDep, email: Annotated[str, Form()] = ""):
    address = accounts.normalize(email)
    # Same answer whether or not the address exists, so the form can't be used to find accounts.
    user = session.exec(select(User).where(func.lower(User.email) == address)).first() if accounts.valid(address) else None
    if user is not None and accounts.is_verified(user) and _can_resend(request):
        accounts.send_reset(request, tasks, user)
        request.session["verify_sent_at"] = time.time()
    flash(request, FORGOT_SENT)
    return RedirectResponse("/forgot-password", status_code=303)


@router.get("/reset-password", response_class=HTMLResponse)
def reset_form(request: Request, session: SessionDep, token: str = ""):
    user = accounts.reset_user(session, token)
    return render(request, "reset.html", me=None, token=token, valid=user is not None, MIN_PASSWORD=MIN_PASSWORD)


@router.post("/reset-password")
def reset(request: Request, session: SessionDep, token: Annotated[str, Form()] = "", password: Annotated[str, Form()] = ""):
    user = accounts.reset_user(session, token)
    if user is None:
        flash(request, "重設連結無效或已過期，請重新申請")
        return RedirectResponse("/forgot-password", status_code=303)
    if len(password) < MIN_PASSWORD:
        flash(request, f"密碼至少 {MIN_PASSWORD} 個字元")
        return RedirectResponse(f"/reset-password?token={token}", status_code=303)
    user.password_hash = hash_password(password)
    session.add(user)
    session.commit()
    request.session.clear()
    flash(request, "密碼已更新，請用新密碼登入")
    return RedirectResponse("/login", status_code=303)
