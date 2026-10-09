import re
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.auth import CurrentUser, hash_password, safe_next, verify_password
from app.db import SessionDep
from app.models import User
from app.templating import render

router = APIRouter()

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
MIN_PASSWORD = 8


def _login(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, me: CurrentUser):
    if me:
        return RedirectResponse("/me/collection", status_code=303)
    return render(request, "register.html", me=None, form={})


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
):
    username = username.strip().lower()
    display_name = display_name.strip()[:30] or username
    error = None
    if not USERNAME_RE.match(username):
        error = "帳號需為 3–20 個英文小寫字母、數字或底線"
    elif len(password) < MIN_PASSWORD:
        error = f"密碼至少 {MIN_PASSWORD} 個字元"
    elif session.exec(select(User).where(User.username == username)).first():
        error = "這個帳號已經有人使用"
    if error:
        form = {"username": username, "display_name": display_name}
        return render(request, "register.html", status_code=400, me=None, form=form, error=error)

    user = User(username=username, display_name=display_name, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    _login(request, user)
    return RedirectResponse("/me/collection", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, me: CurrentUser, next: str = ""):
    if me:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "login.html", me=None, next=next, form={})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "",
):
    username = username.strip().lower()
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None or not verify_password(password, user.password_hash):
        form = {"username": username}
        error = "帳號或密碼錯誤"
        return render(request, "login.html", status_code=400, me=None, next=next, form=form, error=error)
    _login(request, user)
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
