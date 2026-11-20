"""拍照找書: barcode / typed ISBN / photo of a cover or copyright page -> the book's public page (/w/{id}).

Barcodes are read in the browser (BarcodeDetector) and arrive here as a typed ISBN would. Photos are read
by the Claude API when ANTHROPIC_API_KEY is set (app.services.vision); otherwise the page offers only
barcodes and typed ISBNs. A recognised book is stored as a Work (no collection entry) so its public page
works; adding it to the collection stays the user's choice on that page.
"""

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import isbn as isbns
from app.auth import RequiredUser
from app.db import SessionDep
from app.models import Category, User
from app.services import books, vision
from app.templating import flash, render
from app.works import upsert_work

router = APIRouter(prefix="/books/scan")

PHOTO_LIMIT = 20  # photo reads per user per hour: each one is a paid API call
_photo_log: dict[int, deque[float]] = defaultdict(deque)
MAX_CANDIDATES = 6


def _page(request: Request, me: User, *, status_code: int = 200, **context):
    context.setdefault("error", None)
    context.setdefault("read", None)
    context.setdefault("candidates", [])
    context.setdefault("query", "")
    return render(request, "book_scan.html", status_code=status_code, me=me, ai_ready=vision.configured(),
                  books_source=books.active_source(), **context)


def _open(session, book: books.Book) -> RedirectResponse:
    work = upsert_work(
        session, category=Category.book, source=book.source, external_id=book.external_id, title=book.title,
        creator=book.authors or None, cover_url=book.cover_url, year=book.year,
    )
    session.commit()
    return RedirectResponse(f"/w/{work.id}", status_code=303)


def _photo_allowed(user_id: int) -> bool:
    now = time.monotonic()
    log = _photo_log[user_id]
    while log and now - log[0] > 3600:
        log.popleft()
    if len(log) >= PHOTO_LIMIT:
        return False
    log.append(now)
    return True


def _rank(candidates: list[books.Book], author: str) -> list[books.Book]:
    """Books whose author shares a name with what the photo shows come first; search order otherwise."""
    names = [n for n in author.replace("，", "、").replace(",", "、").replace("/", "、").split("、") if n.strip()]
    if not names:
        return candidates
    hit = lambda b: any(n.strip() in b.authors for n in names)  # noqa: E731
    return sorted(candidates, key=lambda b: not hit(b))


@router.get("", response_class=HTMLResponse)
def scan_page(request: Request, me: RequiredUser):
    return _page(request, me)


@router.post("/isbn")
async def by_isbn(request: Request, session: SessionDep, me: RequiredUser, isbn: Annotated[str, Form()] = ""):
    isbn13 = isbns.normalize(isbn) or next(iter(isbns.find_all(isbn)), None)
    if not isbn13:
        return _page(request, me, status_code=422,
                     error=f"「{isbn.strip()[:40]}」不是有效的 ISBN。ISBN 是 10 或 13 碼，印在封底條碼上方或版權頁。")
    try:
        book = await books.lookup_isbn(isbn13)
    except books.BooksError:
        return _page(request, me, status_code=503, error="書籍資料庫暫時無法連線，請稍後再試")
    if book is None:
        return _page(request, me, status_code=404,
                     error=f"書籍資料庫裡沒有 ISBN {isbns.pretty(isbn13)}。可以改用書名搜尋，或拍版權頁讓系統讀書名。")
    return _open(session, book)


@router.post("/photo")
async def by_photo(request: Request, session: SessionDep, me: RequiredUser, photo: UploadFile | None = File(None)):
    if not vision.configured():
        return _page(request, me, status_code=503,
                     error="伺服器尚未設定 ANTHROPIC_API_KEY，暫時不能辨識照片。請改掃條碼或輸入 ISBN。")
    if photo is None or not photo.filename:
        return _page(request, me, status_code=422, error="請先拍一張照片或選一張圖片。")
    data = await photo.read(vision.MAX_UPLOAD + 1)
    if not data:
        return _page(request, me, status_code=422, error="請先拍一張照片或選一張圖片。")
    if len(data) > vision.MAX_UPLOAD:
        return _page(request, me, status_code=413, error="照片太大了（上限 12 MB），請重拍或換一張。")
    if not _photo_allowed(me.id):
        return _page(request, me, status_code=429, error="照片辨識一小時最多 20 次，請稍後再試，或改用條碼、ISBN。")

    try:
        read = await vision.read_book(data)
    except vision.NotAnImage:
        return _page(request, me, status_code=422, error="讀不了這個檔案，請上傳 JPG、PNG 等照片。")
    except vision.VisionError:
        return _page(request, me, status_code=503, error="照片辨識暫時無法使用，請稍後再試，或改用條碼、ISBN。")

    # 1) An ISBN on the photo is exact: open that book if any source knows it.
    try:
        for isbn13 in isbns.find_all(read.isbn):
            book = await books.lookup_isbn(isbn13)
            if book:
                return _open(session, book)
    except books.BooksError:
        pass  # fall through to a title search

    # 2) Otherwise search by what the photo says and let the user confirm: editions and translations differ.
    if not read.title:
        message = "照片裡好像不是一本書。" if not read.is_book else "照片裡讀不到書名或 ISBN，請拍清楚一點，或改拍版權頁。"
        return _page(request, me, status_code=422, error=message, read=read)
    try:
        found = await books.search(read.title)
    except books.BooksError:
        return _page(request, me, status_code=503, error="書籍資料庫暫時無法連線，請稍後再試", read=read)
    candidates = _rank(found, read.author)[:MAX_CANDIDATES]
    return _page(request, me, read=read, candidates=candidates, query=read.title,
                 error=None if candidates else f"書籍資料庫裡找不到「{read.title}」。")


@router.post("/pick")
async def pick(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    source: Annotated[str, Form()],
    book_id: Annotated[str, Form()],
):
    if source not in (books.GOOGLE, books.OPENLIBRARY):
        raise HTTPException(status_code=400)
    try:
        book = await books.get_book(source, book_id)
    except books.BooksError:
        flash(request, "書籍資料庫暫時無法連線，請稍後再試")
        return RedirectResponse("/books/scan", status_code=303)
    if book is None:
        raise HTTPException(status_code=404)
    return _open(session, book)
