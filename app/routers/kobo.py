from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from app import kobo
from app.auth import RequiredUser
from app.db import SessionDep
from app.templating import flash, render

router = APIRouter(prefix='/me/kobo')


@router.get('')
def page(request: Request, me: RequiredUser):
    return render(request, 'kobo.html', me=me)


@router.post('/import')
def import_books(request: Request, session: SessionDep, me: RequiredUser,
                 payload: Annotated[str, Form()] = '', text: Annotated[str, Form()] = '',
                 status: Annotated[str, Form()] = 'reading'):
    try:
        rows = kobo.parse_metadata(payload) if payload else kobo.parse_text(text, status)
        if not rows:
            raise kobo.KoboFormatError('沒有找到書籍，請選擇檔案或貼上書名。')
    except kobo.KoboFormatError as e:
        return render(request, 'kobo.html', me=me, error=str(e), status_code=400)
    added, skipped = kobo.import_books(session, me, rows)
    flash(request, f'新增 {added} 本，略過 {skipped} 本已收藏書籍。新書確認後才會依你的公開設定顯示。')
    return RedirectResponse('/me/review/book' if added else '/me/collection#book', status_code=303)
