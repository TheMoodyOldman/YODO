"""Parse Google Takeout exports for YouTube / YouTube Music.

- watch-history.json: every watched video. Only music plays are kept (YouTube Music, or
  auto-generated "Artist - Topic" channels on regular YouTube); everything else is dropped here
  and never stored.
- music library songs.csv: saved songs. Header names are localized ("影片 ID" / "Video ID"),
  so columns are read by position: video id, song, album, artist 1..7.
"""

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

TAIPEI = timezone(timedelta(hours=8))

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TITLE_PREFIX_RE = re.compile(r"^(Watched|已觀看|觀看了)\s*")
_TOPIC_SUFFIX = " - Topic"


class TakeoutFormatError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # "html" | "invalid"


@dataclass
class Track:
    video_id: str
    title: str
    artist: str

    @property
    def cover_url(self) -> str:
        return f"https://i.ytimg.com/vi/{self.video_id}/mqdefault.jpg"


@dataclass
class WatchHistory:
    tracks: dict[str, Track]  # video_id -> track (most recent metadata)
    plays: Counter[tuple[str, str]]  # (video_id, "YYYY-MM") -> plays
    skipped: int  # non-music or unusable entries


def _video_id(url: str | None) -> str | None:
    if not url:
        return None
    ids = parse_qs(urlparse(url).query).get("v")
    return ids[0] if ids and _VIDEO_ID_RE.match(ids[0]) else None


def parse_watch_history(data: bytes) -> WatchHistory:
    if data.lstrip()[:1] == b"<":
        raise TakeoutFormatError("html")
    try:
        items = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise TakeoutFormatError("invalid") from e
    if not isinstance(items, list) or (items and not any(isinstance(i, dict) and "time" in i for i in items[:50])):
        raise TakeoutFormatError("invalid")

    tracks: dict[str, Track] = {}
    plays: Counter[tuple[str, str]] = Counter()
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        subtitles = item.get("subtitles") or [{}]
        channel = (subtitles[0].get("name") or "").strip() if isinstance(subtitles[0], dict) else ""
        is_music = item.get("header") == "YouTube Music" or channel.endswith(_TOPIC_SUFFIX)
        video_id = _video_id(item.get("titleUrl"))
        try:
            played_at = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00")).astimezone(TAIPEI)
        except (KeyError, ValueError):
            played_at = None
        if not (is_music and video_id and channel and played_at):
            skipped += 1
            continue

        if video_id not in tracks:  # history is newest-first, so this keeps the latest title
            title = _TITLE_PREFIX_RE.sub("", item.get("title") or "").strip()
            tracks[video_id] = Track(video_id, title or video_id, channel.removesuffix(_TOPIC_SUFFIX).strip())
        plays[(video_id, played_at.strftime("%Y-%m"))] += 1
    return WatchHistory(tracks=tracks, plays=plays, skipped=skipped)


def parse_library_csv(data: bytes) -> list[Track]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise TakeoutFormatError("invalid") from e
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 4:
        raise TakeoutFormatError("invalid")

    tracks = []
    for row in rows[1:]:
        if len(row) < 4 or not _VIDEO_ID_RE.match(row[0]):
            continue
        artist = next((a.strip() for a in row[3:] if a.strip()), "")
        tracks.append(Track(row[0], row[1].strip() or row[0], artist))
    if len(rows) > 1 and not tracks:
        raise TakeoutFormatError("invalid")
    return tracks
