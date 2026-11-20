import secrets
import time
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from app import book_import, kobo
from app.auth import RequiredUser
from app.config import settings
from app.db import SessionDep
from app.services import google_books
from app.templating import flash

router = APIRouter(prefix='/me')
BACK = '/me/collection#book'
SESSION_KEY = 'google_books_oauth'


def back():
    return RedirectResponse(BACK, status_code=303, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@router.post('/books/import')
async def paste(request: Request, session: SessionDep, me: RequiredUser,
                text: Annotated[str, Form()] = '', status: Annotated[str, Form()] = 'reading'):
    try:
        rows = kobo.parse_text(text, status)
        if not rows:
            raise kobo.KoboFormatError('請先貼上至少一本書名。')
    except kobo.KoboFormatError as e:
        from app.routers.me import collection
        request.state.kobo_error, request.state.kobo_text, request.state.kobo_status = str(e), text, status
        return await collection(request, session, me)
    added, skipped = book_import.import_books(session, me, rows, source='manual')
    flash(request, f'新增 {added} 本，略過 {skipped} 本已收藏書籍。確認後才會公開。')
    return RedirectResponse('/me/review/book' if added else BACK, status_code=303)


@router.get('/google-books/connect')
def connect(request: Request, me: RequiredUser, include_owned: bool = False):
    if not google_books.configured():
        flash(request, 'Google 書櫃連結尚未開放，請先使用貼上書單。')
        return back()
    uri = settings.google_books_redirect_uri or (
        settings.public_url.rstrip('/') + '/me/google-books/callback' if settings.public_url else str(request.url_for('google_books_callback')))
    parsed = urlparse(uri)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        flash(request, 'Google 授權網址設定有誤，請聯絡網站管理者。')
        return back()
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    request.session[SESSION_KEY] = {'state': state, 'verifier': verifier, 'user': me.id,
        'at': time.time(), 'redirect_uri': uri, 'include_owned': include_owned}
    return RedirectResponse(google_books.authorization_url(uri, state, verifier), status_code=303,
                            headers={'Cache-Control': 'no-store'})


@router.get('/google-books/callback', name='google_books_callback')
async def callback(request: Request, session: SessionDep, me: RequiredUser,
                   state: str = '', code: str = '', error: str = ''):
    pending = request.session.pop(SESSION_KEY, None)
    if (not isinstance(pending, dict) or pending.get('user') != me.id
        or not isinstance(pending.get('state'), str) or not secrets.compare_digest(state, pending['state'])
        or not 0 <= time.time() - pending.get('at', 0) < 600):
        flash(request, 'Google 授權已失效，請重新連結。')
        return back()
    if error or not code:
        flash(request, '已取消 Google 書櫃匯入，你仍可使用貼上書單。')
        return back()
    try:
        rows, truncated = await google_books.read_library(code, pending['redirect_uri'], pending['verifier'], pending['include_owned'])
    except google_books.GoogleBooksError:
        flash(request, 'Google 書櫃暫時無法匯入，請稍後重試或使用貼上書單。')
        return back()
    if not rows:
        flash(request, '這些 Google 書架沒有可匯入的書；可重新選擇包含購買清單，或貼上自己的書單。')
        return back()
    added, skipped = book_import.import_books(session, me, rows, source='googlebooks')
    flash(request, f'Google 書櫃新增 {added} 本，略過 {skipped} 本已收藏書籍。確認後才會公開。'
          + ('本次最多帶入 1000 本，部分書籍未匯入。' if truncated else ''))
    return RedirectResponse('/me/review/book' if added else BACK, status_code=303,
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
