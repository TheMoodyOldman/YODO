from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.anime import TAG_COLORS, TAG_GROUPS, TIER_COLORS, TIER_LABELS, TIERS
from app.db import engine
from app.models import CATEGORY_LABELS, VISIBILITY_LABELS, Category, Visibility
from app.social import Relation, incoming_request_count

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def ago(dt: datetime) -> str:
    """「3 小時前」-style relative time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite hands back naive UTC datetimes
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return "剛剛"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分鐘前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小時前"
    if seconds < 7 * 86400:
        return f"{int(seconds // 86400)} 天前"
    return dt.astimezone().strftime("%Y-%m-%d")


STATIC_DIR = Path(__file__).parent / "static"


def asset(path: str) -> str:
    """Static URL with the file's mtime as a version, so browsers pick up CSS/JS edits immediately."""
    try:
        version = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        version = 0
    return f"/static/{path}?v={version}"


def challenge_label(note: str | None) -> str:
    """Feed text for a 30 天挑戰 pick, from its "<kind>:<day>" note."""
    from app.challenge import PROMPTS, TITLES, parse_kind

    kind, _, day = (note or "").partition(":")
    category = parse_kind(kind)
    if category is None or not day.isdigit() or not 1 <= int(day) <= len(PROMPTS[category]):
        return "參加了 30 天挑戰"
    return f"{TITLES[category]} Day {day}：{PROMPTS[category][int(day) - 1]}"


def avatar_hue(user_id: int) -> int:
    return (user_id * 67) % 360  # stable, well-spread color per user


templates.env.filters["ago"] = ago
templates.env.globals.update(
    Category=Category,
    Visibility=Visibility,
    Relation=Relation,
    CATEGORY_LABELS=CATEGORY_LABELS,
    VISIBILITY_LABELS=VISIBILITY_LABELS,
    UNITS={Category.game: "款", Category.anime: "部", Category.music: "首"},
    ANIME_TIERS=TIERS,
    TIER_LABELS=TIER_LABELS,
    ANIME_TAG_GROUPS=TAG_GROUPS,
    TIER_COLORS=TIER_COLORS,
    TAG_COLORS=TAG_COLORS,
    avatar_hue=avatar_hue,
    asset=asset,
    challenge_label=challenge_label,
)


def flash(request: Request, message: str) -> None:
    """Show a one-time message on the next rendered page."""
    request.session["flash"] = message


def render(request: Request, name: str, status_code: int = 200, **context: Any):
    context.setdefault("flash", request.session.pop("flash", None))
    me = context.get("me")
    if me is not None and "friend_requests" not in context:
        with Session(engine) as session:  # nav badge for pending friend requests
            context["friend_requests"] = incoming_request_count(session, me.id)
    return templates.TemplateResponse(request, name, context, status_code=status_code)
