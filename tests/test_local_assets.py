"""Demo mode without the network (LOCAL_ASSETS_DIR): pages and the Recap / share-card renderer use
the downloaded copy of a cover when there is one and the original URL otherwise; off by default;
scripts.cache_covers collects the database's URLs and downloads them (fake HTTP)."""

import asyncio
import io
import json
import os
import pathlib
import shutil
import sqlite3

here = pathlib.Path(__file__).parent
db = here / "test_local_assets.db"
assets = here / "test_local_assets_dir"
db.unlink(missing_ok=True)
shutil.rmtree(assets, ignore_errors=True)
assets.mkdir()
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["LOCAL_ASSETS_DIR"] = str(assets)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import card_render, local_assets  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CollectionEntry, User, Work  # noqa: E402
from scripts import cache_covers  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def jpeg(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 12), color).save(buf, "JPEG")
    return buf.getvalue()


init_db()
HAVE = "https://img.test/covers/have.jpg"
MISSING = "https://img.test/covers/missing.png"
STEAM = "https://cdn.test/steam/apps/10/library_600x900.jpg"
(assets / local_assets.file_name(HAVE)).write_bytes(jpeg("red"))
(assets / local_assets.file_name(STEAM.replace("library_600x900.jpg", "header.jpg"))).write_bytes(jpeg("blue"))

check("file names keep the extension and are stable",
      local_assets.file_name(HAVE).endswith(".jpg") and local_assets.file_name(HAVE) == local_assets.file_name(HAVE)
      and local_assets.file_name("https://x.test/a?b=1").endswith(".bin"))
check("url_for: local copy when downloaded", local_assets.url_for(HAVE) == f"/local-assets/{local_assets.file_name(HAVE)}")
check("url_for: original URL when not downloaded", local_assets.url_for(MISSING) == MISSING)
check("url_for: leaves empty and local URLs alone", local_assets.url_for(None) is None and local_assets.url_for("/photos/1") == "/photos/1")

c = TestClient(app)
c.post("/register", data={"username": "alice", "email": "alice@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
with Session(engine) as s:
    alice = s.exec(select(User).where(User.username == "alice")).one()
    for i, (cat, src, url) in enumerate(((Category.anime, "anilist", HAVE), (Category.anime, "anilist", MISSING),
                                          (Category.game, "steam", STEAM))):
        w = Work(category=cat, source=src, external_id=str(i), title=f"W{i}", cover_url=url)
        s.add(w)
        s.flush()
        s.add(CollectionEntry(user_id=alice.id, work_id=w.id, playtime_minutes=600 if cat == Category.game else None))
    s.commit()

page = c.get("/u/alice").text
check("profile uses the local copy", f'src="/local-assets/{local_assets.file_name(HAVE)}"' in page)
check("profile falls back to the original URL", f'src="{MISSING}"' in page)
check("Steam fallback image points to its local copy",
      f'data-fallback="/local-assets/{local_assets.file_name(STEAM.replace("library_600x900.jpg", "header.jpg"))}"' in page)
r = c.get(f"/local-assets/{local_assets.file_name(HAVE)}")
check("local copy is served", r.status_code == 200 and r.content == (assets / local_assets.file_name(HAVE)).read_bytes()
      and r.headers["content-type"].startswith("image/jpeg"))
check("collection rating dialog cover uses the local copy", f'data-cover="/local-assets/{local_assets.file_name(HAVE)}"' in c.get("/me/collection").text)

# Recap / share cards: local file read without the network; missing ones still fetched
asked = []


async def fake_get(self, url, *a, **k):
    asked.append(url)
    raise httpx.ConnectError("offline")


real_get = httpx.AsyncClient.get
httpx.AsyncClient.get = fake_get
try:
    images = asyncio.run(card_render.fetch_images({HAVE, MISSING}))
finally:
    httpx.AsyncClient.get = real_get
check("card renderer reads the local copy, no request for it", HAVE in images and images[HAVE].size == (8, 12) and HAVE not in asked)
check("card renderer still tries the network for missing ones (and copes offline)", MISSING in asked and MISSING not in images)

# off by default: nothing changes
settings.local_assets_dir = ""
try:
    check("demo mode off: original URLs", local_assets.url_for(HAVE) == HAVE and f'src="{HAVE}"' in c.get("/u/alice").text)
finally:
    settings.local_assets_dir = str(assets)

# cache_covers: collect + download (fake HTTP), skipping what's there
src_db = here / "test_local_assets_src.db"
src_db.unlink(missing_ok=True)
con = sqlite3.connect(src_db)
con.executescript("""
CREATE TABLE work (id INTEGER PRIMARY KEY, source VARCHAR, cover_url VARCHAR, preview_url VARCHAR);
CREATE TABLE catalogcache (key VARCHAR PRIMARY KEY, payload VARCHAR, fetched_at DATETIME);
""")
con.execute("INSERT INTO work VALUES (1, 'anilist', 'https://a.test/1.jpg', NULL)")
con.execute("INSERT INTO work VALUES (2, 'lastfm', NULL, 'https://a.test/clip.m4a')")
con.execute("INSERT INTO work VALUES (3, 'steam', 'https://a.test/steam/library_600x900.jpg', NULL)")
con.execute("INSERT INTO work VALUES (4, 'lastfm', '/photos/3', NULL)")
con.execute("INSERT INTO catalogcache VALUES ('season:2026-FALL', ?, '2026-11-20')",
            (json.dumps([{"id": 1, "cover_url": "https://a.test/s1.png"}, {"id": 2, "cover_url": "https://a.test/broken.jpg"}]),))
con.commit()
con.close()
urls = cache_covers.collect_urls(src_db)
check("collects covers, previews, Steam fallback and season list; skips local paths",
      urls == {"https://a.test/1.jpg", "https://a.test/clip.m4a", "https://a.test/steam/library_600x900.jpg",
               "https://a.test/steam/header.jpg", "https://a.test/s1.png", "https://a.test/broken.jpg"}, str(sorted(urls)))


def handler(request):
    if "broken" in str(request.url):
        return httpx.Response(404)
    return httpx.Response(200, content=b"bytes:" + str(request.url).encode())


out = here / "test_local_assets_out"
shutil.rmtree(out, ignore_errors=True)


async def run_download():
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await cache_covers.download(urls, out, client)


got, had, failed = asyncio.run(run_download())
check("downloads all, reports the failure", got == 5 and had == 0 and failed == ["https://a.test/broken.jpg"])
check("files named like the pages expect", (out / local_assets.file_name("https://a.test/clip.m4a")).read_bytes() == b"bytes:https://a.test/clip.m4a"
      and not list(out.glob("*.part")))
got, had, failed = asyncio.run(run_download())
check("second run skips what's already there", got == 0 and had == 5 and len(failed) == 1)

# Work pages in demo mode: facts come from the database after the first lookup, covers are local
from app import workinfo  # noqa: E402
from app.models import CatalogCache  # noqa: E402
from app.services import anilist as anilist_service  # noqa: E402

BIG = "https://img.test/covers/big.jpg"
(assets / local_assets.file_name(BIG)).write_bytes(jpeg("green"))
lookups = []


async def fake_details(anilist_id):
    lookups.append(anilist_id)
    return {"description": "一段介紹", "genres": ["Drama"], "episodes": 12, "seasonYear": 2026,
            "coverImage": {"extraLarge": BIG, "color": "#e4a15d"}, "siteUrl": "https://anilist.test/x"}


anilist_service.get_details = fake_details
with Session(engine) as s:
    have = s.exec(select(Work).where(Work.cover_url == HAVE)).one()
    work_id, ext = have.id, have.external_id
url = f"/u/alice/w/{work_id}"
page = c.get(url).text
check("work page: first visit looks the work up once and keeps it", lookups == [int(ext)] and "一段介紹" in page)
with Session(engine) as s:
    check("work page facts stored in the database", s.get(CatalogCache, f"workinfo:anilist:{ext}") is not None)


async def offline(*a, **k):
    raise AssertionError("work page must not call AniList in demo mode once cached")


anilist_service.get_details = offline
page = c.get(url).text
check("work page: later visits need no network (served from the database)", "一段介紹" in page and lookups == [int(ext)])
big_local = f"/local-assets/{local_assets.file_name(BIG)}"
check("work page: big cover and backdrop use the local copy", f'src="{big_local}"' in page and f"url('{big_local}')" in page
      and "https://img.test/" not in page.split("<body", 1)[1].replace('content="https://img.test', ""))
pub = c.get(f"/w/{work_id}").text
check("public work page uses the local copy too", f'src="{big_local}"' in pub)

# a new server process has an empty in-memory cache: the database copy still answers
async def no_network_lookup(work):
    raise AssertionError("lookup called")


real_lookup = workinfo._lookup
workinfo._lookup = no_network_lookup
try:
    with Session(engine) as s:
        info = asyncio.run(workinfo.get_work_info(s.get(Work, work_id), s))
    check("restart-safe: database copy used without any lookup", info.description == "一段介紹" and info.image == BIG
          and isinstance(info.facts[0], tuple))
finally:
    workinfo._lookup = real_lookup

# cache_covers also downloads the work pages' big covers
con = sqlite3.connect(src_db)
con.execute("INSERT INTO catalogcache VALUES ('workinfo:anilist:9', ?, '2026-11-20')", (json.dumps({"image": "https://a.test/big9.jpg"}),))
con.commit()
con.close()
check("cache_covers collects work-page covers", "https://a.test/big9.jpg" in cache_covers.collect_urls(src_db))

for p in (src_db,):
    p.unlink(missing_ok=True)
shutil.rmtree(out, ignore_errors=True)
shutil.rmtree(assets, ignore_errors=True)
print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
