import asyncio
import os
import pathlib

here = pathlib.Path(__file__).parent
db = here / "test_zh.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["TMDB_API_KEY"] = ""  # the panel must explain a missing key

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import anime_search, zh  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Work  # noqa: E402
from app.services import anilist, bangumi, books  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


# ---------- zh helpers ----------
check("t2s", zh.to_simplified("三體 孤獨搖滾") == "三体 孤独摇滚")
check("s2tw", zh.to_traditional("葬送的芙莉莲") == "葬送的芙莉蓮")
check("japanese untouched", zh.to_traditional("ぼっち・ざ・ろっく！") == "ぼっち・ざ・ろっく！" and not zh.is_chinese("進撃の巨人"))
check("english untouched", zh.to_simplified("Frieren") == "Frieren" and not zh.is_chinese("Frieren"))

# ---------- anime search with fakes ----------
SUBJECTS = [bangumi.Subject(1, "ぼっち・ざ・ろっく！", "孤独摇滚！"), bangumi.Subject(2, "ぼっち・ざ・ろっく！ 第2期", "孤独摇滚！第二季")]
CATALOG = {
    "ぼっち・ざ・ろっく！": [anilist.Anime(130003, "BOCCHI THE ROCK!", "ぼっち・ざ・ろっく！", None, 2022, "TV")],
    "ぼっち・ざ・ろっく！ 第2期": [anilist.Anime(999, "BOCCHI THE ROCK! Season 2", "ぼっち・ざ・ろっく！ 第２期", None, 2026, "TV"),
                              anilist.Anime(130003, "BOCCHI THE ROCK!", "ぼっち・ざ・ろっく！", None, 2022, "TV")],
}
calls = {"bangumi": [], "anilist": []}


async def fake_bangumi(keyword, limit=6):
    calls["bangumi"].append(keyword)
    if keyword == "down":
        raise bangumi.BangumiError("down")
    return [s for s in SUBJECTS if keyword in (s.name, "孤独摇滚")] if keyword != "孤独摇滚" else SUBJECTS


async def fake_anilist(text):
    calls["anilist"].append(text)
    return [anilist.Anime(a.id, a.title, a.original_title, a.cover_url, a.year, a.format) for a in CATALOG.get(text, [])]


async def fake_get_anime(anilist_id):
    return next((anilist.Anime(a.id, a.title, a.original_title, None, a.year, a.format)
                 for hits in CATALOG.values() for a in hits if a.id == anilist_id), None)


bangumi.search_anime = fake_bangumi
anilist.search_anime = fake_anilist
anilist.get_anime = fake_get_anime

res = asyncio.run(anime_search.search("孤獨搖滾"))
check("chinese query goes to bangumi in simplified", calls["bangumi"][-1] == "孤独摇滚")
check("anilist searched by japanese names", calls["anilist"] == ["ぼっち・ざ・ろっく！", "ぼっち・ざ・ろっく！ 第2期"], calls["anilist"])
check("results deduped, chinese titles in traditional", [(a.id, a.title) for a in res] == [(130003, "孤獨搖滾！"), (999, "孤獨搖滾！第二季")],
      [(a.id, a.title) for a in res])
calls["anilist"].clear()
res = asyncio.run(anime_search.search("BOCCHI"))
check("english query skips bangumi", calls["anilist"] == ["BOCCHI"])
check("chinese_title by native", asyncio.run(anime_search.chinese_title("ぼっち・ざ・ろっく！")) == "孤獨搖滾！")
check("chinese_title never raises", asyncio.run(anime_search.chinese_title("down")) is None)

# ---------- books: both scripts ----------
# This is the Open Library path (no Google Books key); don't let a key in .env switch sources.
from app.config import settings  # noqa: E402

settings.google_books_api_key = ""
seen_q = []


async def fake_get(url, params):
    seen_q.append(params.get("q"))
    if params.get("q") == "三体" or params.get("q") == '"三体"':
        return {"docs": [{"key": "/works/OL1W", "title": "三体", "author_name": ["刘慈欣"], "cover_i": 1}]}
    return {"docs": []}


books._get = fake_get
res = asyncio.run(books.search("三體"))
check("book search tries traditional then simplified", seen_q == ['"三體"', '"三体"'], seen_q)
check("book shown in traditional", [(b.title, b.authors) for b in res] == [("三體", "劉慈欣")], [(b.title, b.authors) for b in res])


# ---------- Netflix: episode grouping and anime routing ----------
from app import netflix  # noqa: E402
from app.services import tmdb  # noqa: E402

csv_text = """Title,Date
"坂本日常: 京","8/31/25"
"坂本日常: 三試","9/5/25"
"比爾·伯爾：紙老虎","12/14/23"
"比爾·伯爾：慢走不送","12/17/23"
"躲在超市後門抽菸的兩人: 抽菸 1","7/14/26"
"""
parsed = {(t.name, t.is_series): t.views for t in netflix.parse_viewing_history(csv_text.encode())}
check("recurring show prefix groups episodes", parsed.get(("坂本日常", True)) == 2, parsed)
check("full-width colon stays part of a title", ("比爾·伯爾：紙老虎", False) in parsed and ("比爾·伯爾：慢走不送", False) in parsed, parsed)

TMDB = {
    "坂本日常": [tmdb.Title("tv:1", "坂本日常", "SAKAMOTO DAYS", None, 2025, "tv", (16, 10759), "ja")],
    "比爾·伯爾：紙老虎": [tmdb.Title("movie:2", "比爾·伯爾：紙老虎", "Bill Burr: Paper Tiger", None, 2019, "movie", (35,), "en")],
    "躲在超市後門抽菸的兩人": [tmdb.Title("tv:3", "躲在超市後門抽菸的兩人", "スーパーの裏でヤニ吸うふたり", None, 2026, "tv", (16,), "ja")],
}


async def fake_tmdb(query, prefer=None):
    return TMDB.get(query, [])


CATALOG["SAKAMOTO DAYS"] = [anilist.Anime(177709, "SAKAMOTO DAYS", "SAKAMOTO DAYS", None, 2025, "TV")]
rate_limited = {"n": 0}
orig_fake_anilist = fake_anilist


async def flaky_anilist(text):
    if text == "SAKAMOTO DAYS" and rate_limited["n"] == 0:
        rate_limited["n"] += 1
        raise anilist.AniListError("rate limited", retry_after=0)
    return await orig_fake_anilist(text)


tmdb.search = fake_tmdb
anilist.search_anime = flaky_anilist
titles = netflix.parse_viewing_history(csv_text.encode())
matches = {t.name: asyncio.run(netflix._match(t, asyncio.Semaphore(5), asyncio.Semaphore(2))) for t in titles}
m = matches["坂本日常"]
check("japanese animation goes to anime (after a rate-limit retry)",
      m and (m.category.value, m.external_id, m.title, m.chinese_title) == ("anime", "177709", "坂本日常", True) and rate_limited["n"] == 1,
      m)
check("other titles stay film", matches["比爾·伯爾：紙老虎"].category.value == "film")
lone = matches["躲在超市後門抽菸的兩人: 抽菸 1"]
check("lone episode falls back to the show name; anime without AniList match stays film",
      lone and lone.category.value == "film" and lone.external_id == "tv:3", lone)

# ---------- app: add anime stores chinese title; background fills old ones ----------
with TestClient(app) as c:
    c.post("/register", data={"username": "zhuser", "email": str("zhuser").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    page = c.get("/me/collection?q=孤獨搖滾").text
    check("collection shows chinese result", "孤獨搖滾！" in page and "可用中文、英文或日文片名搜尋" in page)
    c.post("/me/collection/anime", data={"anilist_id": "130003", "q": ""})
    with Session(engine) as s:
        w = s.exec(select(Work).where(Work.external_id == "130003")).one()
        check("added anime stored with chinese title", (w.title, w.original_title) == ("孤獨搖滾！", "ぼっち・ざ・ろっく！"), (w.title, w.original_title))
        w.title, w.zh_checked_at = "BOCCHI THE ROCK!", None  # an anime added before this feature
        s.add(w)
        s.commit()
    anime_search.BANGUMI_DELAY = 0
    with Session(engine) as s:
        n = asyncio.run(anime_search.enrich_titles(s))
        w = s.exec(select(Work).where(Work.external_id == "130003")).one()
        check("background fills chinese title", n == 1 and w.title == "孤獨搖滾！" and w.zh_checked_at is not None)
        check("checked works not retried", asyncio.run(anime_search.enrich_titles(s)) == 0)

    page = c.get("/me/collection").text
    check("netflix panel explains missing key up front", "暫時無法匯入 Netflix 紀錄" in page and 'action="/me/netflix/import"' not in page)
    check("upload buttons show busy state", 'data-busy="匯入中…"' in page)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
