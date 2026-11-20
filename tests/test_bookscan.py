"""拍照找書: ISBN parsing, ISBN lookup, photo reading (faked Claude API) and the /books/scan pages."""

import io
import os
import pathlib
import sqlite3

db = pathlib.Path(__file__).parent / "test_bookscan.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
os.environ["ANTHROPIC_API_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import isbn  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import bookscan  # noqa: E402
from app.services import books, vision  # noqa: E402


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def q(sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# ---------- ISBN parsing (pure) ----------
check("ISBN-13 with hyphens", isbn.normalize("978-0-306-40615-7") == "9780306406157")
check("ISBN-10 converted to 13", isbn.normalize("0-306-40615-2") == "9780306406157")
check("ISBN-10 with X check digit", isbn.normalize("ISBN 0-8044-2957-x") == "9780804429573")
check("wrong check digit refused", isbn.normalize("9780306406158") is None)
check("not 978/979 refused", isbn.normalize("1234567890128") is None)
check("found on a copyright page, phone numbers ignored",
      isbn.find_all("電話 02-2392-6899 傳真 0223926899 ISBN 978-0-306-40615-7（平裝）定價 380 元") == ["9780306406157"])
check("barcode price add-on not swallowed", isbn.find_all("9780306406157 90000") == ["9780306406157"])
check("same book as 10 and 13 counted once", isbn.find_all("ISBN 0306406152 / 978-0-306-40615-7") == ["9780306406157"])
check("pretty form", isbn.pretty("9780306406157") == "978-030640615-7")
# 978-986-7778-17-8: its first ten digits 9789867778 are a valid ISBN-10 by chance, which once opened a
# different book (978-978986777-6) when OCR broke the number. A cut-off number must find nothing.
check("odd spacing still reads the whole ISBN-13", isbn.find_all("ISBN 978 - 986 - 7778 - 17 - 8") == ["9789867778178"])
check("ISBN-13 never cut into a lookalike ISBN-10",
      isbn.find_all("ISBN 978-986-7778:17-8") == [] and isbn.find_all("ISBN 978-986-7778-1") == [])
check("typed ISBN-10 still accepted", isbn.normalize("0-8044-2957-X") == "9780804429573")

# ---------- photo reply parsing and image prep (pure) ----------
r = vision.parse_reply('好的：{"isbn": "978-0-306-40615-7", "title": "三體", "author": "劉慈欣", "publisher": "貓頭鷹", "is_book": true}')
check("reply parsed from JSON with chatter around it", (r.isbn, r.title, r.author, r.is_book) == ("978-0-306-40615-7", "三體", "劉慈欣", True))
check("not-a-book flag", vision.parse_reply('{"title": "", "is_book": false}').is_book is False)
try:
    vision.parse_reply("I can't read this.")
    check("no JSON -> VisionError", False)
except vision.VisionError:
    check("no JSON -> VisionError", True)
big = io.BytesIO()
Image.new("RGB", (4000, 3000), "white").save(big, "PNG")
jpeg = vision.prepare_image(big.getvalue())
check("photo shrunk to JPEG ≤ 1568px", Image.open(io.BytesIO(jpeg)).size == (1568, 1176) and jpeg[:2] == b"\xff\xd8")
try:
    vision.prepare_image(b"not an image")
    check("garbage refused", False)
except vision.NotAnImage:
    check("garbage refused", True)

# ---------- fakes for the network ----------
BOOKS = {
    "OL1W": books.Book(books.OPENLIBRARY, "OL1W", "三體", "劉慈欣", None, 2008),
    "OL2W": books.Book(books.OPENLIBRARY, "OL2W", "三體 II：黑暗森林", "劉慈欣", None, 2008),
    "OL9W": books.Book(books.OPENLIBRARY, "OL9W", "三體研究", "某評論家", None, 2015),
}
BY_ISBN = {"9780306406157": "OL1W"}
LOOKUPS = []
READS = []
NEXT_READ = {}


async def fake_lookup(isbn13):
    LOOKUPS.append(isbn13)
    key = BY_ISBN.get(isbn13)
    return BOOKS[key] if key else None


async def fake_search(query):
    return [b for b in (BOOKS["OL9W"], BOOKS["OL1W"], BOOKS["OL2W"]) if query in b.title]


async def fake_get_book(source, external_id):
    return BOOKS.get(external_id)


async def fake_details(source, external_id):
    return {"description": "地球文明與三體文明的接觸。", "categories": ["科幻"], "page_count": 300,
            "publisher": "測試出版社", "link": "https://openlibrary.org/works/" + external_id}


async def fake_read(photo):
    READS.append(len(photo))
    return vision.BookText(**NEXT_READ)


books.lookup_isbn, books.search, books.get_book, books.get_details = fake_lookup, fake_search, fake_get_book, fake_details
vision.read_book = fake_read


def photo_file():
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), "gray").save(buf, "JPEG")
    return {"photo": ("book.jpg", buf.getvalue(), "image/jpeg")}


with TestClient(app) as alice, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": "alice@test.yodo", "password": "testpass123",
                                  "birth_date": "2000-01-01"})

    r = anon.get("/books/scan", follow_redirects=False)
    check("scanner needs login", r.status_code in (302, 303, 307) and "/login" in r.headers.get("location", ""))
    r = alice.get("/books/scan")
    check("scanner page: ISBN form, photo form, AI on", r.status_code == 200 and 'action="/books/scan/isbn"' in r.text
          and 'action="/books/scan/photo"' in r.text and 'data-ai="1"' in r.text)
    check("collection book panel links to the scanner", 'href="/books/scan"' in alice.get("/me/collection").text)

    # ---------- typed / barcode ISBN
    r = alice.post("/books/scan/isbn", data={"isbn": "0-306-40615-2"}, follow_redirects=False)
    check("ISBN-10 -> looked up as 13 -> public page", r.status_code == 303 and r.headers["location"].startswith("/w/")
          and LOOKUPS[-1] == "9780306406157")
    work_id = int(r.headers["location"].split("/")[-1])
    check("book stored as a work, not added to the collection",
          q("SELECT title, creator FROM work WHERE id=?", work_id) == [("三體", "劉慈欣")]
          and q("SELECT COUNT(*) FROM collectionentry")[0][0] == 0)
    page = alice.get(f"/w/{work_id}").text
    check("public page shows the book's details", "三體" in page and "劉慈欣" in page and "地球文明" in page)
    r = alice.post("/books/scan/isbn", data={"isbn": "978-0-306-40615-7"}, follow_redirects=False)
    check("same book again -> same work", r.headers["location"] == f"/w/{work_id}" and q("SELECT COUNT(*) FROM work")[0][0] == 1)

    r = alice.post("/books/scan/isbn", data={"isbn": "12345"})
    check("invalid ISBN explained", r.status_code == 422 and "不是有效的 ISBN" in r.text)
    r = alice.post("/books/scan/isbn", data={"isbn": "9780804429573"})
    check("unknown ISBN explained", r.status_code == 404 and "沒有 ISBN 978-080442957-3" in r.text)

    # ---------- photo: ISBN on the photo
    NEXT_READ.update(isbn="ISBN 978-0-306-40615-7", title="三體", author="劉慈欣", publisher="", is_book=True)
    r = alice.post("/books/scan/photo", files=photo_file(), follow_redirects=False)
    check("photo with ISBN -> straight to the book", r.status_code == 303 and r.headers["location"] == f"/w/{work_id}")

    # ---------- photo: cover only -> candidates, author match first
    NEXT_READ.update(isbn="", title="三體", author="劉慈欣", publisher="貓頭鷹", is_book=True)
    r = alice.post("/books/scan/photo", files=photo_file())
    text = r.text
    check("cover -> read text shown + candidates to confirm", "照片上讀到的文字" in text and "就是這本" in text and "貓頭鷹" in text)
    check("author's books ranked before the namesake study", text.index('value="OL1W"') < text.index('value="OL9W"'))
    r = alice.post("/books/scan/pick", data={"source": "openlibrary", "book_id": "OL2W"}, follow_redirects=False)
    check("picked candidate -> its page", r.status_code == 303 and q("SELECT title FROM work WHERE id=?",
          int(r.headers["location"].split("/")[-1])) == [("三體 II：黑暗森林",)])
    check("pick refuses unknown sources", alice.post("/books/scan/pick", data={"source": "x", "book_id": "1"}).status_code == 400)

    NEXT_READ.update(isbn="", title="", author="", publisher="", is_book=False)
    r = alice.post("/books/scan/photo", files=photo_file())
    check("not a book -> said so", r.status_code == 422 and "不是一本書" in r.text)
    NEXT_READ.update(isbn="", title="不存在的書", author="", publisher="", is_book=True)
    r = alice.post("/books/scan/photo", files=photo_file())
    check("unknown title -> link to a full search", "找不到「不存在的書」" in r.text and "bq=" in r.text)
    r = alice.post("/books/scan/photo", files={"photo": ("x.jpg", b"", "image/jpeg")})
    check("empty upload refused", r.status_code == 422)

    # ---------- limits and configuration
    reads_before = len(READS)
    bookscan._photo_log.clear()
    for _ in range(bookscan.PHOTO_LIMIT):
        alice.post("/books/scan/photo", files=photo_file())
    r = alice.post("/books/scan/photo", files=photo_file())
    check("photo reads capped per hour", r.status_code == 429 and len(READS) - reads_before == bookscan.PHOTO_LIMIT)

    settings.anthropic_api_key = ""
    r = alice.get("/books/scan")
    check("without a key: page says photos need setup", 'data-ai="0"' in r.text and "需要伺服器設定照片辨識" in r.text)
    r = alice.post("/books/scan/photo", files=photo_file())
    check("without a key: photo refused, ISBN still works", r.status_code == 503
          and alice.post("/books/scan/isbn", data={"isbn": "9780306406157"}, follow_redirects=False).status_code == 303)
