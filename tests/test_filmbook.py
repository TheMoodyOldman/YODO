import os
import pathlib
import re
import sqlite3
from datetime import date

db = pathlib.Path(__file__).parent / "test_fb.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["TMDB_API_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.netflix import parse_viewing_history, split_title  # noqa: E402
from app.services import books, tmdb  # noqa: E402

FILMS = {
    "movie:603": tmdb.Title("movie:603", "駭客任務", "The Matrix", "https://img.test/matrix.jpg", 1999, "movie"),
    "tv:66732": tmdb.Title("tv:66732", "怪奇物語", "Stranger Things", None, 2016, "tv"),
    "movie:27205": tmdb.Title("movie:27205", "全面啟動", "Inception", None, 2010, "movie"),
}
BY_NAME = {"駭客任務": "movie:603", "The Matrix": "movie:603", "Stranger Things": "tv:66732", "怪奇物語": "tv:66732",
           "Inception": "movie:27205"}
SEARCHES = []


async def fake_search(query, prefer=None):
    SEARCHES.append((query, prefer))
    key = BY_NAME.get(query)
    return [FILMS[key]] if key else []


async def fake_title(external_id):
    return FILMS.get(external_id)


async def fake_tmdb_details(external_id):
    return {"_kind": "movie", "overview": "<b>選擇</b>紅色藥丸", "runtime": 136, "release_date": "1999-03-31",
            "genres": [{"name": "動作"}, {"name": "科幻"}], "vote_average": 8.2,
            "credits": {"crew": [{"job": "Director", "name": "華卓斯基姊妹"}], "cast": [{"name": "基努李維"}]}}


BOOKS = {"OL1W": books.Book(books.OPENLIBRARY, "OL1W", "三體", "劉慈欣", None, 2008),
         "OL2W": books.Book(books.OPENLIBRARY, "OL2W", "Project Hail Mary", "Andy Weir", None, 2021),
         "OL3W": books.Book(books.OPENLIBRARY, "OL3W", "活著", "余華", None, 1993)}


async def fake_book_search(q):
    return [b for b in BOOKS.values() if q.casefold() in b.title.casefold() or q in b.authors]


async def fake_get_book(source, external_id):
    return BOOKS.get(external_id)


tmdb.search, tmdb.get_title, tmdb.get_details = fake_search, fake_title, fake_tmdb_details
books.search, books.get_book = fake_book_search, fake_get_book


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def q(sql, *args):
    con = sqlite3.connect(db)
    try:
        r = con.execute(sql, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


# ---------- Netflix parsing (pure) ----------
check("English episode -> show", split_title("Stranger Things: Season 1: Chapter One: The Vanishing of Will Byers") == ("Stranger Things", True))
check("Chinese episode (full-width colons) -> show", split_title("怪奇物語：第 1 季：第一章：威爾的失蹤") == ("怪奇物語", True))
check("two-part episode title", split_title("The Crown: Season 2") == ("The Crown", True))
check("movie with a colon stays whole", split_title("Star Wars: The Last Jedi") == ("Star Wars: The Last Jedi", False))
check("plain movie", split_title("The Matrix") == ("The Matrix", False))
us = "Title,Date\n\"Stranger Things: Season 1: Chapter One\",10/1/26\n\"Stranger Things: Season 1: Chapter Two\",10/2/26\n\"The Matrix\",9/30/26\n".encode()
titles = {t.name: t for t in parse_viewing_history(us)}
check("US M/D/YY dates, episodes merged", titles["Stranger Things"].views == 2 and titles["Stranger Things"].months == {"2026-10": 2}
      and titles["The Matrix"].months == {"2026-09": 1})
eu = "Title,Date\n\"The Matrix\",13/09/2026\n\"The Matrix\",01/10/2026\n".encode("utf-8-sig")
check("D/M/YYYY detected from a day > 12", {t.name: t.months for t in parse_viewing_history(eu)}["The Matrix"] == {"2026-09": 1, "2026-10": 1})
tw = "標題,日期\n\"怪奇物語：第 1 季：第一章\",2026/10/3\n".encode()
check("zh-TW YYYY/M/D", parse_viewing_history(tw)[0].months == {"2026-10": 1})
try:
    parse_viewing_history(b"not,a\nvalid,file\n")
    check("garbage refused", False)
except Exception:
    check("garbage refused", True)

with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anon:
    for c, n in ((alice, "alice"), (bob, "bob")):
        c.post("/register", data={"username": n, "email": str(n).lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    r = alice.get("/me/collection")
    check("影視 and 書籍 tabs exist", 'data-tab="film"' in r.text and 'data-tab="book"' in r.text and "匯入 Netflix" in r.text)

    # ---------- film: search, add, rate
    r = alice.get("/me/collection", params={"fq": "駭客任務"})
    check("film search shows results on the film tab", 'data-default="film"' in r.text and "駭客任務" in r.text and "電影" in r.text)
    r = alice.post("/me/collection/film", data={"tmdb_id": "movie:603", "fq": "駭客任務"}, follow_redirects=False)
    check("add film -> rating dialog", "rate=" in r.headers["location"] and r.headers["location"].endswith("#film"))
    page = alice.get(r.headers["location"].split("#")[0]).text
    film_dialog = page.split('id="rate-dialog-film"')[1].split("</dialog>")[0]
    check("film dialog uses film tags, not anime ones", "#燒腦" in film_dialog and "#廁紙" not in film_dialog and 'data-category="film"' in page)
    film_entry = q("SELECT e.id FROM collectionentry e JOIN work w ON w.id=e.work_id WHERE w.external_id='movie:603'")[0][0]
    alice.post(f"/me/collection/{film_entry}/verdict", data={"tier": "must_watch", "tag": "廁紙"})
    check("anime-only tag refused on a film", q("SELECT tier, tag FROM collectionentry WHERE id=?", film_entry) == [("must_watch", None)])
    alice.post(f"/me/collection/{film_entry}/verdict", data={"tier": "must_watch", "tag": "燒腦"})
    check("film tier + tag saved", q("SELECT tier, tag FROM collectionentry WHERE id=?", film_entry) == [("must_watch", "燒腦")])

    # ---------- books: search, add, status + rating
    r = alice.get("/me/collection", params={"bq": "三體"})
    check("book search on the book tab", 'data-default="book"' in r.text and "劉慈欣" in r.text)
    ids = {}
    for bid, status, tier in (("OL1W", "read", "great"), ("OL2W", "reading", "must_watch"), ("OL3W", "want", "")):
        r = alice.post("/me/collection/book", data={"source": "openlibrary", "book_id": bid, "bq": "x"}, follow_redirects=False)
        ids[bid] = int(re.search(r"rate=(\d+)", r.headers["location"]).group(1))
        alice.post(f"/me/collection/{ids[bid]}/verdict", data={"status": status, "tier": tier, "tag": "一口氣讀完" if bid == "OL1W" else ""})
    check("book status saved", q("SELECT status FROM collectionentry WHERE id=?", ids["OL2W"]) == [("reading",)])
    alice.post(f"/me/collection/{ids['OL3W']}/verdict", data={"status": "lost", "tier": ""})
    check("invalid status cleared", q("SELECT status FROM collectionentry WHERE id=?", ids["OL3W"]) == [(None,)])
    alice.post(f"/me/collection/{ids['OL3W']}/verdict", data={"status": "want"})
    check("book author stored as creator", q("SELECT creator FROM work WHERE external_id='OL1W'") == [("劉慈欣",)])
    page = alice.get("/me/collection").text
    book_dialog = page.split('id="rate-dialog-book"')[1].split("</dialog>")[0]
    check("book dialog has status chips + book tags", 'name="status" value="reading"' in book_dialog and "#一口氣讀完" in book_dialog)

    prof = anon.get("/u/alice").text
    book_panel = prof.split('data-panel="book"')[1].split('role="tabpanel"')[0]
    headings = re.findall(r'<h3 class="tier-heading">([^<]+?) <', book_panel)
    check("books grouped 讀完 → 在讀 → 想讀", headings == ["讀完", "在讀", "想讀"])
    check("status chip on cards", 'class="status-chip status-read">讀完' in prof)
    film_panel = prof.split('data-panel="film"')[1].split('role="tabpanel"')[0]
    check("films grouped by tier", "此生必看" in film_panel and "駭客任務" in film_panel)

    # ---------- work page
    film_work = q("SELECT id FROM work WHERE external_id='movie:603'")[0][0]
    r = alice.get(f"/u/alice/w/{film_work}")
    check("film page: TMDB facts, overview tags stripped, film picker",
          all(t in r.text for t in ("華卓斯基姊妹", "136 分鐘", "基努李維", "選擇紅色藥丸")) and "<b>選擇" not in r.text
          and "#燒腦" in r.text and "關於這部作品" in r.text)
    book_work = q("SELECT id FROM work WHERE external_id='OL1W'")[0][0]
    r = anon.get(f"/u/alice/w/{book_work}")
    check("book page shows status + author", "讀完" in r.text and "劉慈欣" in r.text and "關於這本書" in r.text)

    # ---------- feed wording
    bob.post("/friends/alice/request")
    alice.post("/friends/bob/accept")
    feed = bob.get("/feed").text
    check("feed says 部作品 / 本書", "把這部作品加進收藏" in feed and "把這本書加進收藏" in feed)

    # ---------- Netflix import
    csv_data = ("Title,Date\n" + "\n".join(
        [f"\"Stranger Things: Season 1: Chapter {i}\",10/{i}/26" for i in range(1, 5)]
        + ["\"Inception\",9/20/26", "\"Unknown Indie Film\",9/21/26"])).encode()
    r = alice.post("/me/netflix/import", files={"history": ("NetflixViewingHistory.csv", csv_data, "text/csv")})
    check("import -> review page, unmatched reported", str(r.url).endswith("/me/review/film") and "找不到（例如《Unknown Indie Film》）" in r.text
          and "新增 2 部" in r.text)
    check("series searched as tv, movies as movie", ("Stranger Things", "tv") in SEARCHES and ("Inception", "movie") in SEARCHES)
    check("imported works wait for review", "怪奇物語" not in anon.get("/u/alice").text)
    pend = re.findall(r'name="publish" value="(\d+)"', r.text)
    alice.post("/me/review/film", data={"publish": pend})
    prof = anon.get("/u/alice").text
    check("after review: shown with episode count", "怪奇物語" in prof and "全面啟動" in prof)
    st = q("SELECT e.play_count FROM collectionentry e JOIN work w ON w.id=e.work_id WHERE w.external_id='tv:66732'")[0][0]
    check("4 episodes -> watched 4 times", st == 4)
    alice.post("/me/netflix/import", files={"history": ("NetflixViewingHistory.csv", csv_data, "text/csv")})
    check("re-import doesn't double count", q("SELECT e.play_count FROM collectionentry e JOIN work w ON w.id=e.work_id WHERE w.external_id='tv:66732'")[0][0] == 4)
    show = q("SELECT id FROM work WHERE external_id='tv:66732'")[0][0]
    check("film page shows monthly views", "每月觀看次數" in anon.get(f"/u/alice/w/{show}").text)
    r = alice.post("/me/netflix/import", files={"history": ("x.csv", b"garbage", "text/csv")})
    check("bad file -> friendly error", "NetflixViewingHistory.csv" in r.text)

    # ---------- privacy + matching
    alice.post("/me/settings", data={"display_name": "alice", "visibility_film": "private", "visibility_game": "public",
                                     "visibility_anime": "public", "visibility_music": "public", "visibility_book": "public", "show_in_match": "1"})
    check("private film category hidden", "駭客任務" not in anon.get("/u/alice").text and anon.get(f"/u/alice/w/{film_work}").status_code == 404)
    check("settings lists the new categories", "影視" in alice.get("/me/settings").text and "書籍" in alice.get("/me/settings").text)

    from app.config import settings

    settings.tmdb_api_key = ""
    r = alice.post("/me/netflix/import", files={"history": ("NetflixViewingHistory.csv", csv_data, "text/csv")})
    check("no TMDB key -> clear message", "尚未設定 TMDB_API_KEY" in r.text)
    check("film search explains missing key", "尚未設定 TMDB_API_KEY" in alice.get("/me/collection").text)
