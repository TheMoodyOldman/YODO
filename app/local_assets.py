"""Demo mode without the network: covers and song previews served from a local folder.

When LOCAL_ASSETS_DIR is set (e.g. "demo_assets", filled by `python -m scripts.cache_covers`),
every external cover / preview URL is first looked up there by a hash of the URL; if the file is
missing the original URL is used, so nothing breaks. Unset (the default), nothing changes.
"""

import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from app.config import settings

MOUNT = "/local-assets"
KNOWN_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".m4a", ".mp3", ".aac"}


def folder() -> Path | None:
    return Path(settings.local_assets_dir) if settings.local_assets_dir else None


def file_name(url: str) -> str:
    """Stable local name for a URL: sha1 prefix + the URL's own extension (for the content type)."""
    suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + (suffix if suffix in KNOWN_SUFFIXES else ".bin")


def local_path(url: str | None) -> Path | None:
    """The downloaded copy of `url`, if demo mode is on and the file exists."""
    base = folder()
    if not base or not url or not url.startswith(("http://", "https://")):
        return None
    path = base / file_name(url)
    return path if path.is_file() else None


def url_for(url: str | None) -> str | None:
    """What a page should load: the local copy when there is one, otherwise `url` unchanged."""
    path = local_path(url)
    return f"{MOUNT}/{path.name}" if path else url
