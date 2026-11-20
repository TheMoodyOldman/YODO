"""Read a book photo (cover, back cover, copyright page) with the Claude API.

Returns what is printed: ISBN, title, author, publisher. Nothing is stored; the photo goes to the API
once and is dropped. Optional: without ANTHROPIC_API_KEY, configured() is False and the scanner falls
back to barcodes and typed ISBNs.
"""

import base64
import io
import json
import re
from dataclasses import dataclass

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

API_URL = "https://api.anthropic.com/v1/messages"
MAX_EDGE = 1568  # long edge sent to the model; larger images cost more without reading better
MAX_UPLOAD = 12 * 1024 * 1024

PROMPT = """這是一張書的照片，可能是封面、封底（含條碼）或版權頁。
請只根據照片上實際印出的文字回答，不要猜測或補上照片裡沒有的資訊。
只回傳一個 JSON 物件，不要加說明或 Markdown：
{"isbn": "照片上的 ISBN，只要數字與 X，沒有就填空字串",
 "title": "書名（含副標題），沒有就填空字串",
 "author": "作者，多位用、分隔，沒有就填空字串",
 "publisher": "出版社，沒有就填空字串",
 "is_book": true 或 false（照片裡看起來是不是一本書）}"""


class VisionError(Exception):
    pass


class NotAnImage(VisionError):
    pass


@dataclass
class BookText:
    isbn: str
    title: str
    author: str
    publisher: str
    is_book: bool


def configured() -> bool:
    return bool(settings.anthropic_api_key)


def prepare_image(data: bytes) -> bytes:
    """JPEG, upright, long edge ≤ MAX_EDGE, no EXIF (drops location data). Raises NotAnImage."""
    if len(data) > MAX_UPLOAD:
        raise NotAnImage("too large")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as e:
        raise NotAnImage(str(e)) from e
    img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def parse_reply(text: str) -> BookText:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise VisionError("no JSON in reply")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise VisionError("bad JSON") from e

    def field(name: str) -> str:
        value = data.get(name)
        return value.strip()[:200] if isinstance(value, str) else ""

    return BookText(
        isbn=field("isbn"), title=field("title"), author=field("author"), publisher=field("publisher"),
        is_book=data.get("is_book") is not False,
    )


async def read_book(photo: bytes) -> BookText:
    jpeg = prepare_image(photo)
    body = {
        "model": settings.vision_model,
        "max_tokens": 400,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(jpeg).decode("ascii")}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(API_URL, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise VisionError(str(e)) from e
    if r.status_code != 200:
        raise VisionError(f"HTTP {r.status_code}")
    text = "".join(block.get("text", "") for block in r.json().get("content", []) if block.get("type") == "text")
    return parse_reply(text)
