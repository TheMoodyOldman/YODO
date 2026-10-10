"""Verdicts for anime, film/TV and books: a tier (sortable) plus one optional slang tag, and for
books a reading status. (The module keeps its name from when only anime had verdicts.)

Games and music have no ratings: playtime and play counts are their score.
"""

from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.models import Category


class AnimeTier(StrEnum):
    must_watch = "must_watch"
    great = "great"
    good = "good"
    okay = "okay"
    bad = "bad"
    dropped = "dropped"


# Categories rated with tiers + tags (instead of time spent).
TIERED = {Category.anime, Category.film, Category.book}

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


class BookStatus(StrEnum):
    read = "read"
    reading = "reading"
    want = "want"


BOOK_STATUSES: list[tuple[BookStatus, str]] = [(BookStatus.read, "讀完"), (BookStatus.reading, "在讀"), (BookStatus.want, "想讀")]
STATUS_LABELS = dict(BOOK_STATUSES)
STATUS_COLORS = {BookStatus.read: (145, 60), BookStatus.reading: (210, 75), BookStatus.want: (40, 85)}
_STATUS_RANK = {s: len(BOOK_STATUSES) - i for i, (s, _) in enumerate(BOOK_STATUSES)}

# Common Taiwanese reactions per category. Anime sources: zh.wikipedia「日本動漫迷使用術語列表」, PTT C_Chat.
TAG_GROUPS_BY_CATEGORY: dict[Category, list[tuple[str, list[str]]]] = {
    Category.anime: [
        ("好評", ["神作", "值得二刷", "等續集"]),
        ("心情", ["好甜", "治癒", "笑死", "胃痛", "致鬱"]),
        ("風格", ["我看了什麼", "電波", "中二", "廢萌", "獵奇"]),
        ("吐槽", ["崩", "爛尾", "腰斬", "廁紙"]),
    ],
    Category.film: [
        ("好評", ["神作", "後勁很強", "值得二刷", "冷門好片"]),
        ("心情", ["淚崩", "笑到肚子痛", "療癒", "熱血", "毛骨悚然"]),
        ("風格", ["燒腦", "反轉", "爆米花", "慢熱", "演技炸裂", "配樂神"]),
        ("吐槽", ["看不懂", "爛尾", "拖戲", "劇情殺"]),
    ],
    Category.book: [
        ("好評", ["神作", "一口氣讀完", "後勁很強", "值得重讀", "推坑"]),
        ("心情", ["淚崩", "療癒", "熱血", "毛骨悚然", "笑出聲"]),
        ("風格", ["燒腦", "反轉", "文筆好", "長知識", "慢熱"]),
        ("吐槽", ["難啃", "翻譯可惜", "爛尾", "太長了"]),
    ],
}
TAG_GROUPS = TAG_GROUPS_BY_CATEGORY[Category.anime]  # kept for anime-only callers (bingo prompts)
TAGS_BY_CATEGORY = {c: {t for _, tags in groups for t in tags} for c, groups in TAG_GROUPS_BY_CATEGORY.items()}
TAGS = set().union(*TAGS_BY_CATEGORY.values())
# Each group has a base hue; tags within it step around the wheel so every button differs.
_GROUP_HUES = {"好評": 38, "心情": 320, "風格": 230, "吐槽": 355}
TAG_COLORS: dict[str, tuple[int, int]] = {}
for _groups in TAG_GROUPS_BY_CATEGORY.values():
    for _group, _tags in _groups:
        for _i, _tag in enumerate(_tags):
            TAG_COLORS.setdefault(_tag, ((_GROUP_HUES[_group] + _i * 24) % 360, 65))

# Tags renamed or removed since they were first offered.
_RENAMED_TAGS = {"發糖": "好甜", "作畫崩壞": "崩"}


def parse_tier(value: str | None) -> AnimeTier | None:
    return AnimeTier(value) if value in TIER_LABELS else None


def parse_tag(value: str | None, category: Category = Category.anime) -> str | None:
    return value if value in TAGS_BY_CATEGORY.get(category, set()) else None


def parse_status(value: str | None) -> BookStatus | None:
    return BookStatus(value) if value in STATUS_LABELS else None


def tier_rank(tier: str | None) -> int:
    return _TIER_RANK.get(tier, 0)  # type: ignore[arg-type]


def status_rank(status: str | None) -> int:
    return _STATUS_RANK.get(status, 0)  # type: ignore[arg-type]


def migrate_tags(conn: Connection) -> None:
    """Idempotent: rename old tags, drop ones no longer offered."""
    for old, new in _RENAMED_TAGS.items():
        conn.execute(text("UPDATE collectionentry SET tag = :new WHERE tag = :old"), {"old": old, "new": new})
    params = {f"t{i}": tag for i, tag in enumerate(sorted(TAGS))}
    placeholders = ", ".join(f":{k}" for k in params)
    conn.execute(text(f"UPDATE collectionentry SET tag = NULL WHERE tag IS NOT NULL AND tag NOT IN ({placeholders})"), params)
