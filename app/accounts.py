"""Email addresses: verification links and password resets. Links are signed tokens (no tables):
a verification link names the user and the exact address it was sent to, and a reset link is tied
to the current password hash, so it stops working once the password changes."""

import re

from fastapi import BackgroundTasks, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import Session, func, select

from app import mail
from app.config import settings
from app.models import User, utcnow

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$")
VERIFY_HOURS = 48
RESET_MINUTES = 60
RESEND_SECONDS = 60

_verify = URLSafeTimedSerializer(settings.secret_key, salt="yodo-email-verify")
_reset = URLSafeTimedSerializer(settings.secret_key, salt="yodo-password-reset")


def normalize(email: str) -> str:
    return email.strip().lower()


def valid(email: str) -> bool:
    return len(email) <= 254 and EMAIL_RE.fullmatch(email) is not None


def taken(session: Session, email: str, except_user: int | None = None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email)
    if except_user is not None:
        query = query.where(User.id != except_user)
    return session.exec(query).first() is not None


def enforced() -> bool:
    """Social features need a verified email only when mail can actually be sent."""
    return mail.configured()


def is_verified(user: User) -> bool:
    return bool(user.email and user.email_verified_at)


def _base(request: Request) -> str:
    return (settings.public_url or str(request.base_url)).rstrip("/")


def send_verification(request: Request, tasks: BackgroundTasks, user: User) -> None:
    token = _verify.dumps({"u": user.id, "e": user.email})
    link = f"{_base(request)}/verify-email?token={token}"
    tasks.add_task(mail.send, user.email, "驗證你的友多聞 YODO 電子信箱",
                   f"嗨 {user.display_name}，\n\n點下面的連結完成電子信箱驗證（{VERIFY_HOURS} 小時內有效）：\n{link}\n\n"
                   "如果你沒有註冊友多聞 YODO，可以忽略這封信。")


def verify(session: Session, token: str) -> User | None:
    """Mark the address verified; None if the link is bad, expired, or for an address since changed."""
    try:
        data = _verify.loads(token, max_age=VERIFY_HOURS * 3600)
    except (BadSignature, SignatureExpired):
        return None
    user = session.get(User, data.get("u"))
    if user is None or not user.email or user.email != data.get("e"):
        return None
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        session.add(user)
        session.commit()
    return user


def send_reset(request: Request, tasks: BackgroundTasks, user: User) -> None:
    token = _reset.dumps({"u": user.id, "h": user.password_hash[-16:]})
    link = f"{_base(request)}/reset-password?token={token}"
    tasks.add_task(mail.send, user.email, "重設你的友多聞 YODO 密碼",
                   f"嗨 {user.display_name}，\n\n點下面的連結重設密碼（{RESET_MINUTES} 分鐘內有效，只能用一次）：\n{link}\n\n"
                   "如果不是你要求的，可以忽略這封信，密碼不會改變。")


def reset_user(session: Session, token: str) -> User | None:
    try:
        data = _reset.loads(token, max_age=RESET_MINUTES * 60)
    except (BadSignature, SignatureExpired):
        return None
    user = session.get(User, data.get("u"))
    if user is None or user.password_hash[-16:] != data.get("h"):
        return None  # already used: the password (and its hash) changed
    return user
