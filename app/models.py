from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import Column, LargeBinary
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(StrEnum):
    game = "game"
    anime = "anime"
    music = "music"
    film = "film"  # movies and series
    book = "book"


class Visibility(StrEnum):
    public = "public"
    friends = "friends"
    private = "private"


CATEGORY_LABELS = {
    Category.game: "遊戲", Category.anime: "動畫", Category.music: "音樂", Category.film: "影視", Category.book: "書籍",
}
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
    region: str | None = None  # app.matching.REGIONS
    looking_for: str | None = None  # comma-separated app.matching.LOOKING_FOR keys
    hide_from_match: bool | None = None  # opted out of 同好推薦 (None = shown)
    avatar_photo_id: int | None = None  # first UserPhoto, kept in sync by app.photos
    contacts: str | None = None  # JSON, see app.contacts
    onboarding_hidden: bool | None = None  # 新手教學 card dismissed
    tour_state: str | None = None  # 互動教學: None (not offered yet) / active / done / skipped
    email: str | None = Field(default=None, index=True)  # lowercase; unique (checked in app.accounts)
    email_verified_at: datetime | None = None
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
    genres_checked_at: datetime | None = None  # genre/tag lookup done (even if it found nothing)
    preview_url: str | None = None  # 30 s Apple preview for 猜歌
    preview_checked_at: datetime | None = None
    zh_checked_at: datetime | None = None  # Chinese title lookup done (anime)


class CollectionEntry(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "work_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    playtime_minutes: int | None = None  # games
    play_count: int | None = None  # music
    rating: int | None = Field(default=None, ge=1, le=10)  # games / music
    tier: str | None = None  # anime / film / book: app.anime.AnimeTier
    tag: str | None = None  # anime / film / book: one of that category's tags (app.anime)
    status: str | None = None  # books: app.anime.BookStatus
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
    challenge = "challenge"  # 30 天挑戰 pick; note = "<kind>:<day>"


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
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Comment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    activity_id: int = Field(foreign_key="activity.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)


class Report(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id", index=True)
    reported_id: int = Field(foreign_key="user.id", index=True)
    reason: str
    detail: str = ""
    resolved: bool | None = None  # set by an admin after review
    created_at: datetime = Field(default_factory=utcnow)


class MatchDismiss(SQLModel, table=True):
    """「不感興趣」: never recommend dismissed_id to user_id again."""

    __table_args__ = (UniqueConstraint("user_id", "dismissed_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    dismissed_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)


class BingoMark(SQLModel, table=True):
    """A manually ticked 興趣賓果 square (auto squares are computed from data, not stored)."""

    __table_args__ = (UniqueConstraint("user_id", "month", "key"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    month: str  # boards change monthly
    key: str
    created_at: datetime = Field(default_factory=utcnow)


class WorkGenre(SQLModel, table=True):
    """Style tags for a work: Steam genres, AniList genres, Last.fm tags (via the artist)."""

    __table_args__ = (UniqueConstraint("work_id", "genre"),)

    id: int | None = Field(default=None, primary_key=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    genre: str
    weight: float = 1.0  # Last.fm tags are weighted by tag strength; others are 1


class Challenge(SQLModel, table=True):
    """A user's 30 天挑戰 run for one category (music / anime / game)."""

    __table_args__ = (UniqueConstraint("user_id", "kind"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    kind: str  # a Category value
    started_on: date
    created_at: datetime = Field(default_factory=utcnow)


class ChallengePick(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("challenge_id", "day"),)

    id: int | None = Field(default=None, primary_key=True)
    challenge_id: int = Field(foreign_key="challenge.id", index=True)
    day: int  # 1..30
    work_id: int = Field(foreign_key="work.id")
    created_at: datetime = Field(default_factory=utcnow)


class GameRoom(SQLModel, table=True):
    """A live multiplayer game (猜誰是臥底, 猜歌). Players poll it; `state` is game-specific JSON."""

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    kind: str  # "undercover" | "song"
    host_id: int = Field(foreign_key="user.id")
    status: str = "lobby"
    state: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RoomPlayer(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("room_id", "user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="gameroom.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    seat: int
    joined_at: datetime = Field(default_factory=utcnow)


# ---------- 作品討論與評分 ----------


class Review(SQLModel, table=True):
    """短評: one per user per work, shown on the public work page."""

    __table_args__ = (UniqueConstraint("user_id", "work_id"),)

    id: int | None = Field(default=None, primary_key=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    spoiler: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ReviewLike(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("review_id", "user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id", index=True)
    user_id: int = Field(foreign_key="user.id")


class WorkComment(SQLModel, table=True):
    """留言區 under a work's public page."""

    id: int | None = Field(default=None, primary_key=True)
    work_id: int = Field(foreign_key="work.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)


class Post(SQLModel, table=True):
    """討論區 sticky note: a thread starter filed under a category, not tied to a work."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    category: Category = Field(index=True)
    body: str
    color: str = "yellow"
    spoiler: bool = False
    reply_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    last_activity_at: datetime = Field(default_factory=utcnow, index=True)


class PostReply(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="post.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)


class UserPhoto(SQLModel, table=True):
    """Profile photo (up to app.photos.MAX_PHOTOS); the lowest position is the avatar."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    position: int = 0
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))  # processed JPEG
    created_at: datetime = Field(default_factory=utcnow)


# ---------- 私訊 ----------


class Message(SQLModel, table=True):
    """One-to-one message between friends (or people connected through 附近朋友)."""

    id: int | None = Field(default=None, primary_key=True)
    sender_id: int = Field(foreign_key="user.id", index=True)
    recipient_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow, index=True)
    read_at: datetime | None = None


# ---------- 附近朋友 ----------


class NearbyPost(SQLModel, table=True):
    """A "say hi nearby" message. Location is only a ~1 km grid point (app.nearby.coarse), never
    the precise position, and the post stops showing after NearbyPost.expires_at."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    lat: float
    lon: float
    radius_km: int
    body: str
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime = Field(index=True)
    cancelled: bool = False


class NearbyReply(SQLModel, table=True):
    """Responding to a nearby post: only then does the poster learn who you are, and you two can chat."""

    __table_args__ = (UniqueConstraint("post_id", "user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="nearbypost.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    body: str
    created_at: datetime = Field(default_factory=utcnow)
