import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, Request

from app.db import SessionDep
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


class LoginRequired(Exception):
    """Raised by require_user; main.py turns it into a redirect to /login."""


def get_current_user(request: Request, session: SessionDep) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None:
        request.session.clear()
    return user


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
