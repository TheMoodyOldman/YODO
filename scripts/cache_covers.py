"""Download every cover and song preview the demo database uses into a local folder, so the demo
runs with LOCAL_ASSETS_DIR set and doesn't wait on AniList, Steam or iTunes (see app.local_assets).

Reads the database with sqlite3 (works' covers and previews, Steam's fallback header image, and
the cached 本季新番 lists). Files already downloaded are skipped. Needs the network.
Usage: .venv\\Scripts\\python.exe -m scripts.cache_covers [database] [folder]
       (defaults: demo.db  demo_assets)
"""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx

from app.local_assets import file_name

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "demo.db"
DEFAULT_DIR = ROOT / "demo_assets"
MAX_BYTES = 8 * 1024 * 1024
CONCURRENCY = 6


def collect_urls(db: Path) -> set[str]:
    con = sqlite3.connect(db)
    urls: set[str] = set()
    for source, cover, preview in con.execute("SELECT source, cover_url, preview_url FROM work"):
        for url in (cover, preview):
            if url and url.startswith(("http://", "https://")):
                urls.add(url)
        if source == "steam" and cover:  # the page falls back to this when the portrait art is missing
            urls.add(cover.replace("library_600x900.jpg", "header.jpg"))
    try:
        for (payload,) in con.execute("SELECT payload FROM catalogcache WHERE key LIKE 'season:%'"):
            urls |= {i["cover_url"] for i in json.loads(payload) if i.get("cover_url")}
    except sqlite3.OperationalError:
        pass  # database without the cache table
    con.close()
    return urls


async def download(urls: set[str], folder: Path, client: httpx.AsyncClient | None = None) -> tuple[int, int, list[str]]:
    """Returns (downloaded, already there, failed URLs)."""
    folder.mkdir(parents=True, exist_ok=True)
    todo = [u for u in sorted(urls) if not (folder / file_name(u)).is_file()]
    failed: list[str] = []
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(c: httpx.AsyncClient, url: str) -> None:
        async with gate:
            try:
                r = await c.get(url)
                if r.status_code != 200 or not r.content or len(r.content) > MAX_BYTES:
                    failed.append(url)
                    return
                tmp = folder / (file_name(url) + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(folder / file_name(url))  # never leave a half-written file behind
            except httpx.HTTPError:
                failed.append(url)

    if client is None:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            await asyncio.gather(*(one(c, u) for u in todo))
    else:
        await asyncio.gather(*(one(client, u) for u in todo))
    return len(todo) - len(failed), len(urls) - len(todo), failed


def main(argv: list[str]) -> int:
    db = Path(argv[0]) if argv else DEFAULT_DB
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_DIR
    if not db.exists():
        print(f"{db} doesn't exist (build it with python -m scripts.seed_demo)")
        return 1
    urls = collect_urls(db)
    got, had, failed = asyncio.run(download(urls, folder))
    size = sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) / 1024 / 1024
    print(f"{len(urls)} covers/previews: {got} downloaded, {had} already there, {len(failed)} failed "
          f"({folder.name}/ is {size:.1f} MB)")
    for url in failed[:10]:
        print("  failed:", url)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
