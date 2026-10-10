from datetime import date, datetime, timezone
from enum import StrEnum

from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(StrEnum):
    game = "game"
    anime = "anime"
    music = "music"


class Visibility(StrEnum):
    public = "public"
    friends = "friends"
    private = "private"


CATEGORY_LABELS = {Category.game: "遊戲", Category.anime: "動畫", Category.music: "音樂"}
VISIBILITY_LABELS = {Visibility.public: "所有人", Visibility.friends: "好友", Visibility.private: "僅自己"}


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)  # used in the profile URL
    display_name: str
    password_hash: str
    bio: str = ""
    steam_id: str | None = None
    lastfm_username: str | None = None
    lastfm_synced_at: datetime | None = None
    birth_date: date | None = None  # age check only (18+ service); never shown
    created_at: datetime = Field(default_factory=utcnow)


class CategoryPrivacy(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "category"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    category: Category
    visibility: Visibility = Visibility.public


class Work(SQLModel, table=True):
    """A game / anime / music item, keyed by its external database ID."""

    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    category: Category = Field(index=True)
    source: str  # steam, anilist, bangumi, lastfm, musicbrainz
    external_id: str
    title: str
    original_title: str | None = None
    creator: str | None = None  # artist for music
    cover_url: str | None = None
    year: int | None = None


class CollectionEntry(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "work_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    playtime_minutes: int | None = None  # games
    play_count: int | None = None  # music
    rating: int | None = Field(default=None, ge=1, le=10)  # games / music
    tier: str | None = None  # anime: app.anime.AnimeTier
    tag: str | None = None  # anime: one of app.anime.TAGS
    hidden: bool = False
    pending_review: bool = False  # imported/synced items await user confirmation before going public
    added_at: datetime = Field(default_factory=utcnow)


class MonthlyPlays(SQLModel, table=True):
    """Play count of one work for one user in one month (Taiwan time). Feeds rankings and monthly cards."""

    __table_args__ = (UniqueConstraint("user_id", "work_id", "month"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    month: str  # "YYYY-MM"
    plays: int


class MonthlyPlaytime(SQLModel, table=True):
    """Game playtime within one month. Steam only reports lifetime totals, so each sync records
    the total at the month's first observation (start) and the latest one (end)."""

    __table_args__ = (UniqueConstraint("user_id", "work_id", "month"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    month: str  # "YYYY-MM", Taiwan time
    start_minutes: int
    end_minutes: int


class CardEvent(SQLModel, table=True):
    """Recap card downloads/shares: the MVP's main success metric."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    period: str | None = None  # "month" | "year" | "all" (None: logged before periods existed = month)
    month: str  # the period key: "2026-10" | "2026" | "all"
    action: str  # "share" | "download"
    created_at: datetime = Field(default_factory=utcnow)


class FriendStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"


class Friendship(SQLModel, table=True):
    """One row per pair of users; requester asked, addressee answers."""

    __table_args__ = (UniqueConstraint("requester_id", "addressee_id"),)

    id: int | None = Field(default=None, primary_key=True)
    requester_id: int = Field(foreign_key="user.id", index=True)
    addressee_id: int = Field(foreign_key="user.id", index=True)
    status: FriendStatus = FriendStatus.pending
    created_at: datetime = Field(default_factory=utcnow)
    responded_at: datetime | None = None


class Block(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)

    id: int | None = Field(default=None, primary_key=True)
    blocker_id: int = Field(foreign_key="user.id", index=True)
    blocked_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ActivityKind(StrEnum):
    anime_added = "anime_added"
    anime_rated = "anime_rated"
    played = "played"  # Steam playtime gained (minutes)
    listened = "listened"  # plays this month gained (plays, songs; work = top song)


class Activity(SQLModel, table=True):
    """Feed item. Merged per user/kind/work/day so syncs and chip taps don't spam friends."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    kind: ActivityKind
    work_id: int | None = Field(default=None, foreign_key="work.id")
    day: str  # "YYYY-MM-DD", Taiwan time
    minutes: int | None = None
    plays: int | None = None
    songs: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Comment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)
