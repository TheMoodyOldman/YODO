from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.anime import TAG_COLORS, TAG_GROUPS, TIER_COLORS, TIER_LABELS, TIERS
from app.models import CATEGORY_LABELS, VISIBILITY_LABELS, Category, Visibility

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    Category=Category,
    Visibility=Visibility,
    CATEGORY_LABELS=CATEGORY_LABELS,
    VISIBILITY_LABELS=VISIBILITY_LABELS,
    UNITS={Category.game: "款", Category.anime: "部", Category.music: "首"},
    ANIME_TIERS=TIERS,
    TIER_LABELS=TIER_LABELS,
    ANIME_TAG_GROUPS=TAG_GROUPS,
    TIER_COLORS=TIER_COLORS,
    TAG_COLORS=TAG_COLORS,
)


def flash(request: Request, message: str) -> None:
    """Show a one-time message on the next rendered page."""
    request.session["flash"] = message


def render(request: Request, name: str, status_code: int = 200, **context: Any):
    context.setdefault("flash", request.session.pop("flash", None))
    return templates.TemplateResponse(request, name, context, status_code=status_code)
