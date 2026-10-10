"""LINE / Discord / Instagram handles on a profile. Each one is either shown to friends or hidden;
they are never public, since they let strangers reach the person outside YODO."""

import json
import re
from dataclasses import dataclass

from app.models import User

FRIENDS, HIDDEN = "friends", "hidden"
VISIBILITY = [(FRIENDS, "只給好友看"), (HIDDEN, "不公開")]


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    pattern: re.Pattern
    hint: str
    url: str | None = None  # profile link template
    copy: bool = True


KINDS = [
    Kind("line", "LINE", re.compile(r"[A-Za-z0-9._-]{1,20}"), "LINE ID，例如 yodo_mika"),
    Kind("discord", "Discord", re.compile(r"[a-z0-9._]{2,32}"), "Discord 使用者名稱（小寫）"),
    Kind("instagram", "Instagram", re.compile(r"[A-Za-z0-9._]{1,30}"), "Instagram 帳號，不含 @",
         url="https://www.instagram.com/{}/", copy=False),
]
BY_KEY = {k.key: k for k in KINDS}


@dataclass
class Contact:
    kind: Kind
    value: str
    visibility: str

    @property
    def url(self) -> str | None:
        return self.kind.url.format(self.value) if self.kind.url else None


def load(user: User) -> dict[str, Contact]:
    try:
        raw = json.loads(user.contacts or "{}")
    except ValueError:
        raw = {}
    out = {}
    for key, item in raw.items():
        if key in BY_KEY and isinstance(item, dict) and item.get("v"):
            out[key] = Contact(BY_KEY[key], str(item["v"]), item.get("vis") if item.get("vis") in (FRIENDS, HIDDEN) else FRIENDS)
    return out


def update(user: User, form) -> list[str]:
    """Apply the settings form; returns labels of values that were rejected (left unchanged)."""
    current, bad = load(user), []
    for kind in KINDS:
        value = str(form.get(f"contact_{kind.key}", "")).strip().lstrip("@")
        visibility = str(form.get(f"contact_{kind.key}_vis", FRIENDS))
        if not value:
            current.pop(kind.key, None)
        elif not kind.pattern.fullmatch(value):
            bad.append(kind.label)
        else:
            current[kind.key] = Contact(kind, value, visibility if visibility in (FRIENDS, HIDDEN) else FRIENDS)
    user.contacts = json.dumps({k: {"v": c.value, "vis": c.visibility} for k, c in current.items()}) if current else None
    return bad


def visible(owner: User, viewer: User | None, is_friend: bool) -> list[Contact]:
    """What the viewer may see: everything for the owner, friends-only fields for friends."""
    contacts = load(owner).values()
    if viewer is not None and viewer.id == owner.id:
        return list(contacts)
    return [c for c in contacts if is_friend and c.visibility == FRIENDS]
