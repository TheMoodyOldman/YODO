"""Anime verdicts: a tier (sortable) plus one optional ACG-slang tag.

Games and music have no ratings: playtime and play counts are their score.
"""

from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.engine import Connection


class AnimeTier(StrEnum):
    must_watch = "must_watch"
    great = "great"
    good = "good"
    okay = "okay"
    bad = "bad"
    dropped = "dropped"


# Best first. Rank is used for sorting; unrated sorts last.
TIERS: list[tuple[AnimeTier, str]] = [
    (AnimeTier.must_watch, "此生必看"),
    (AnimeTier.great, "大推"),
    (AnimeTier.good, "還不錯"),
    (AnimeTier.okay, "普通"),
    (AnimeTier.bad, "雷"),
    (AnimeTier.dropped, "已棄坑"),
]
TIER_LABELS = dict(TIERS)
_TIER_RANK = {tier: len(TIERS) - i for i, (tier, _) in enumerate(TIERS)}
# Picker button colors as (hue, saturation %): each choice gets its own color.
TIER_COLORS = {
    AnimeTier.must_watch: (22, 90),
    AnimeTier.great: (275, 70),
    AnimeTier.good: (145, 60),
    AnimeTier.okay: (210, 20),
    AnimeTier.bad: (0, 70),
    AnimeTier.dropped: (0, 0),
}

# Common Taiwanese ACG reactions. Sources: zh.wikipedia「日本動漫迷使用術語列表」, PTT C_Chat.
TAG_GROUPS: list[tuple[str, list[str]]] = [
    ("好評", ["神作", "值得二刷", "等續集"]),
    ("心情", ["好甜", "治癒", "笑死", "胃痛", "致鬱"]),
    ("風格", ["我看了什麼", "電波", "中二", "廢萌", "獵奇"]),
    ("吐槽", ["崩", "爛尾", "腰斬", "廁紙"]),
]
TAGS = {tag for _, tags in TAG_GROUPS for tag in tags}
# Each group has a base hue; tags within it step around the wheel so every button differs.
_GROUP_HUES = {"好評": 38, "心情": 320, "風格": 230, "吐槽": 355}
TAG_COLORS = {
    tag: ((_GROUP_HUES[group] + i * 24) % 360, 65) for group, tags in TAG_GROUPS for i, tag in enumerate(tags)
}

# Tags renamed or removed since they were first offered.
_RENAMED_TAGS = {"發糖": "好甜", "作畫崩壞": "崩"}


def parse_tier(value: str | None) -> AnimeTier | None:
    return AnimeTier(value) if value in TIER_LABELS else None


def parse_tag(value: str | None) -> str | None:
    return value if value in TAGS else None


def tier_rank(tier: str | None) -> int:
    return _TIER_RANK.get(tier, 0)  # type: ignore[arg-type]


def migrate_tags(conn: Connection) -> None:
    """Idempotent: rename old tags, drop ones no longer offered."""
    for old, new in _RENAMED_TAGS.items():
        conn.execute(text("UPDATE collectionentry SET tag = :new WHERE tag = :old"), {"old": old, "new": new})
    params = {f"t{i}": tag for i, tag in enumerate(sorted(TAGS))}
    placeholders = ", ".join(f":{k}" for k in params)
    conn.execute(text(f"UPDATE collectionentry SET tag = NULL WHERE tag IS NOT NULL AND tag NOT IN ({placeholders})"), params)
