"""Profile photos: decoded, rotated upright, center-cropped to 4:5 and re-encoded as JPEG, so
only clean image bytes (no EXIF location) are ever stored or served."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlmodel import Session, col, select

from app.models import User, UserPhoto

MAX_PHOTOS = 4
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
SIZE = (960, 1200)  # 4:5, like dating-app cards
MIN_SIDE = 300
FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}  # MPO: some phone JPEGs


class PhotoError(Exception):
    """Message is shown to the user."""


def process(data: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in FORMATS:
            raise PhotoError("只支援 JPG、PNG、WebP 圖片（iPhone 的 HEIC 請先改存成 JPG）")
        img = ImageOps.exif_transpose(img)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise PhotoError("讀不懂這張圖片，請換一張 JPG 或 PNG") from e
    if min(img.size) < MIN_SIDE:
        raise PhotoError(f"照片太小了，至少要 {MIN_SIDE}×{MIN_SIDE} 像素")
    img = ImageOps.fit(img.convert("RGB"), SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=84, optimize=True, progressive=True)
    return out.getvalue()


def photo_ids(session: Session, user_id: int) -> list[int]:
    """The user's photos in display order (no image bytes loaded)."""
    return list(session.exec(
        select(UserPhoto.id).where(UserPhoto.user_id == user_id).order_by(col(UserPhoto.position), col(UserPhoto.id))
    ).all())


def _renumber(session: Session, user: User, ordered: list[int]) -> None:
    for position, photo_id in enumerate(ordered):
        photo = session.get(UserPhoto, photo_id)
        photo.position = position
        session.add(photo)
    user.avatar_photo_id = ordered[0] if ordered else None
    session.add(user)


def add_photo(session: Session, user: User, data: bytes) -> None:
    ids = photo_ids(session, user.id)
    if len(ids) >= MAX_PHOTOS:
        raise PhotoError(f"最多 {MAX_PHOTOS} 張照片，請先刪掉一張")
    photo = UserPhoto(user_id=user.id, position=len(ids), data=process(data))
    session.add(photo)
    session.flush()
    _renumber(session, user, ids + [photo.id])
    session.commit()


def delete_photo(session: Session, user: User, photo_id: int) -> bool:
    ids = photo_ids(session, user.id)
    if photo_id not in ids:
        return False
    session.delete(session.get(UserPhoto, photo_id))
    session.flush()
    _renumber(session, user, [i for i in ids if i != photo_id])
    session.commit()
    return True


def make_first(session: Session, user: User, photo_id: int) -> bool:
    ids = photo_ids(session, user.id)
    if photo_id not in ids:
        return False
    _renumber(session, user, [photo_id] + [i for i in ids if i != photo_id])
    session.commit()
    return True
