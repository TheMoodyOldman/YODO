import re
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.auth import MIN_AGE, CurrentUser, SessionUser, age_on, hash_password, is_adult, safe_next, verify_password
from app.db import SessionDep
from app.importers.youtube import TAIPEI
from app.models import User
from app.templating import render

router = APIRouter()

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
MIN_PASSWORD = 8
MAX_AGE = 120
UNDERAGE_MSG = f"友多聞 YODO 僅限 {MIN_AGE} 歲以上使用"


def _login(request: Request, user: User) -> None:
    request.session.clear()
    request.session["user_id"] = user.id


def _today() -> date:
    return datetime.now(TAIPEI).date()


def _latest_birth_date() -> str:
    """Upper bound for the date picker: exactly MIN_AGE years ago (Feb 29 -> Feb 28)."""
    t = _today()
    try:
        return t.replace(year=t.year - MIN_AGE).isoformat()
    except ValueError:
        return t.replace(year=t.year - MIN_AGE, day=28).isoformat()


def parse_birth_date(value: str) -> tuple[date | None, str | None]:
    """(birth date, error). Valid dates of under-18s come back with the underage error."""
    try:
        birth = date.fromisoformat(value.strip())
    except ValueError:
        return None, "請填寫出生日期"
    age = age_on(birth, _today())
    if age < 0 or age > MAX_AGE:
        return None, "出生日期看起來不對，請再確認一次"
    if age < MIN_AGE:
        return birth, UNDERAGE_MSG
    return birth, None


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, me: CurrentUser):
    if me:
        return RedirectResponse("/me/collection", status_code=303)
    return render(request, "register.html", me=None, form={}, max_birth=_latest_birth_date())


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
):
    username = username.strip().lower()
    display_name = display_name.strip()[:30] or username
    birth, error = parse_birth_date(birth_date)
    if error is None:
        if not USERNAME_RE.match(username):
            error = "帳號需為 3–20 個英文小寫字母、數字或底線"
        elif len(password) < MIN_PASSWORD:
            error = f"密碼至少 {MIN_PASSWORD} 個字元"
        elif session.exec(select(User).where(User.username == username)).first():
            error = "這個帳號已經有人使用"
    if error:
        # Under-18 sign-ups are refused without storing anything.
        form = {"username": username, "display_name": display_name}
        return render(
            request, "register.html", status_code=400, me=None, form=form, error=error, max_birth=_latest_birth_date()
        )

    user = User(username=username, display_name=display_name, password_hash=hash_password(password), birth_date=birth)
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
    error = None
    if user is None or not verify_password(password, user.password_hash):
        error = "帳號或密碼錯誤"
    elif user.birth_date is not None and not is_adult(user.birth_date):
        error = f"這個帳號未滿 {MIN_AGE} 歲，滿 {MIN_AGE} 歲後就能登入"
    if error:
        return render(request, "login.html", status_code=400, me=None, next=next, form={"username": username}, error=error)
    _login(request, user)
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/me/age", response_class=HTMLResponse)
def age_form(request: Request, me: SessionUser, next: str = ""):
    """Accounts created before the 18+ check confirm their birth date once."""
    if me is None:
        return RedirectResponse("/login", status_code=303)
    if me.birth_date is not None:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "age.html", me=None, next=next, max_birth=_latest_birth_date())


@router.post("/me/age", response_class=HTMLResponse)
def age_submit(
    request: Request,
    session: SessionDep,
    me: SessionUser,
    birth_date: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    if me is None:
        return RedirectResponse("/login", status_code=303)
    birth, error = parse_birth_date(birth_date)
    if birth is None:
        return render(request, "age.html", status_code=400, me=None, next=next, error=error, max_birth=_latest_birth_date())
    me.birth_date = birth
    session.add(me)
    session.commit()
    if error:  # under 18: keep the date so the answer can't simply be changed, and sign out
        request.session.clear()
        return render(request, "age.html", status_code=403, me=None, underage=True, error=error)
    return RedirectResponse(safe_next(next), status_code=303)
