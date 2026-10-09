from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.auth import RequiredUser
from app.db import SessionDep
from app.importers.youtube import TakeoutFormatError, parse_library_csv, parse_watch_history
from app.music import YOUTUBE, clear_source, import_youtube
from app.templating import flash

router = APIRouter(prefix="/me/youtube")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
BACK = "/me/collection#music"

HISTORY_ERRORS = {
    "html": "觀看紀錄是 HTML 格式。請在 Google Takeout 把「YouTube 和 YouTube Music」的記錄格式改成 JSON 後重新匯出。",
    "invalid": "無法讀取觀看紀錄，請上傳 Takeout 裡「觀看記錄」資料夾中的 watch-history.json。",
}
LIBRARY_ERROR = "無法讀取音樂收藏，請上傳 Takeout 裡的 music library songs.csv。"


async def _read(upload: UploadFile | None) -> bytes | None:
    """Return file bytes, None if the input was left empty. Raises ValueError if too large."""
    if upload is None or not upload.filename:
        return None
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError
    return data or None


@router.post("/import")
async def import_takeout(
    request: Request,
    session: SessionDep,
    me: RequiredUser,
    history: UploadFile | None = File(None),
    library: UploadFile | None = File(None),
):
    try:
        history_bytes, library_bytes = await _read(history), await _read(library)
    except ValueError:
        flash(request, "檔案太大了（上限 100 MB）")
        return RedirectResponse(BACK, status_code=303)
    if history_bytes is None and library_bytes is None:
        flash(request, "請選擇要上傳的檔案")
        return RedirectResponse(BACK, status_code=303)

    try:
        parsed_history = parse_watch_history(history_bytes) if history_bytes else None
    except TakeoutFormatError as e:
        flash(request, HISTORY_ERRORS[e.reason])
        return RedirectResponse(BACK, status_code=303)
    try:
        parsed_library = parse_library_csv(library_bytes) if library_bytes else []
    except TakeoutFormatError:
        flash(request, LIBRARY_ERROR)
        return RedirectResponse(BACK, status_code=303)

    if not (parsed_history and parsed_history.tracks) and not parsed_library:
        flash(request, "檔案裡沒有找到音樂播放紀錄或收藏的歌曲")
        return RedirectResponse(BACK, status_code=303)

    result = import_youtube(session, me, parsed_history, parsed_library)
    summary = f"匯入完成：{result.songs_with_plays} 首有播放紀錄，共 {result.total_plays} 次播放"
    if result.new_songs:
        flash(request, f"{summary}。新增 {result.new_songs} 首歌，確認後才會公開")
        return RedirectResponse("/me/music/review", status_code=303)
    flash(request, f"{summary}，沒有新的歌曲")
    return RedirectResponse(BACK, status_code=303)


@router.post("/clear")
def clear(request: Request, session: SessionDep, me: RequiredUser):
    removed = clear_source(session, me, YOUTUBE)
    flash(request, f"已刪除 {removed} 首從 YouTube 匯入的歌曲與播放紀錄")
    return RedirectResponse(BACK, status_code=303)
