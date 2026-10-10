import hashlib
import hmac
import secrets
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, Request

from app.db import SessionDep
from app.importers.youtube import TAIPEI
from app.models import User

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


MIN_AGE = 18


def age_on(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def is_adult(birth: date | None) -> bool:
    return birth is not None and age_on(birth, datetime.now(TAIPEI).date()) >= MIN_AGE


def is_locked(user: User) -> bool:
    """Declared under 18: the account can't log in and its pages aren't shown to anyone."""
    return user.birth_date is not None and not is_adult(user.birth_date)


class LoginRequired(Exception):
    """Raised by require_user; main.py turns it into a redirect to /login."""


class BirthDateRequired(Exception):
    """Logged in, but the account predates the 18+ check; main.py redirects to /me/age."""


def get_session_user(request: Request, session: SessionDep) -> User | None:
    """The logged-in user without the age gate (only for the age form itself)."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or (user.birth_date is not None and not is_adult(user.birth_date)):
        request.session.clear()
        return None
    return user


def get_current_user(user: Annotated[User | None, Depends(get_session_user)]) -> User | None:
    if user is not None and user.birth_date is None:
        raise BirthDateRequired
    return user


SessionUser = Annotated[User | None, Depends(get_session_user)]
CurrentUser = Annotated[User | None, Depends(get_current_user)]


def require_user(user: CurrentUser) -> User:
    if user is None:
        raise LoginRequired
    return user


RequiredUser = Annotated[User, Depends(require_user)]


def safe_next(url: str | None, default: str = "/me/collection") -> str:
    """Only allow same-site relative redirects."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return default
