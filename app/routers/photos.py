from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import photos
from app.auth import CurrentUser, RequiredUser, is_locked
from app.db import SessionDep
from app.models import User, UserPhoto
from app.social import is_blocked
from app.templating import flash, render

router = APIRouter()

BACK = "/me/photos"


@router.get("/photos/{photo_id}")
def photo(session: SessionDep, me: CurrentUser, photo_id: int):
    item = session.get(UserPhoto, photo_id)
    owner = session.get(User, item.user_id) if item else None
    if item is None or owner is None or is_locked(owner) or (me and is_blocked(session, me.id, owner.id)):
        raise HTTPException(status_code=404)
    # A photo id never changes content (edits create a new row), so it can be cached for good.
    return Response(item.data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/me/photos", response_class=HTMLResponse)
def manage(request: Request, session: SessionDep, me: RequiredUser):
    return render(request, "photos.html", me=me, photo_ids=photos.photo_ids(session, me.id), MAX_PHOTOS=photos.MAX_PHOTOS)


@router.post("/me/photos")
async def upload(request: Request, session: SessionDep, me: RequiredUser, photo: UploadFile | None = File(None)):
    if photo is None or not photo.filename:
        flash(request, "請選擇一張照片")
        return RedirectResponse(BACK, status_code=303)
    data = await photo.read(photos.MAX_UPLOAD_BYTES + 1)
    if len(data) > photos.MAX_UPLOAD_BYTES:
        flash(request, "照片太大了（上限 15 MB）")
        return RedirectResponse(BACK, status_code=303)
    try:
        photos.add_photo(session, me, data)
    except photos.PhotoError as e:
        flash(request, str(e))
        return RedirectResponse(BACK, status_code=303)
    flash(request, "已新增照片")
    return RedirectResponse(BACK, status_code=303)


@router.post("/me/photos/{photo_id}/delete")
def delete(request: Request, session: SessionDep, me: RequiredUser, photo_id: int):
    if not photos.delete_photo(session, me, photo_id):
        raise HTTPException(status_code=404)
    flash(request, "已刪除照片")
    return RedirectResponse(BACK, status_code=303)


@router.post("/me/photos/{photo_id}/first")
def first(request: Request, session: SessionDep, me: RequiredUser, photo_id: int):
    if not photos.make_first(session, me, photo_id):
        raise HTTPException(status_code=404)
    flash(request, "已設為大頭照")
    return RedirectResponse(BACK, status_code=303)
