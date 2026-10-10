"""Draw the Recap share card (1080x1920, Instagram Story size) with Pillow."""

import asyncio
import colorsys
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.anime import TIER_COLORS, TIER_LABELS
from app.cards import RecapStats
from app.config import settings
from app.models import Category

W, H = 1080, 1920
MARGIN = 72
PAD = 40  # inside section panels
GAP = 24  # between sections
HEADER_BOTTOM = 345
FOOTER_TOP = H - 110

WHITE = (255, 255, 255)
MUTED = (201, 196, 232)
ACCENT = (185, 176, 255)
PANEL = (255, 255, 255, 24)
PLACEHOLDER = (255, 255, 255, 40)
BG_TOP, BG_BOTTOM = (59, 42, 143), (18, 15, 46)

# CJK-capable fonts: Windows (Microsoft JhengHei), Debian/Ubuntu (Noto CJK), macOS (PingFang).
_FONTS = {
    "regular": ["C:/Windows/Fonts/msjh.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/System/Library/Fonts/PingFang.ttc"],
    "bold": ["C:/Windows/Fonts/msjhbd.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
             "/System/Library/Fonts/PingFang.ttc"],
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@lru_cache(maxsize=64)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    override = settings.card_font_bold if weight == "bold" else settings.card_font_regular
    for path in [override, *_FONTS[weight]]:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)  # no CJK glyphs, but never crash


async def fetch_images(urls: set[str]) -> dict[str, Image.Image]:
    async def one(client: httpx.AsyncClient, url: str) -> tuple[str, Image.Image | None]:
        try:
            r = await client.get(url)
            if r.status_code != 200 or len(r.content) > MAX_IMAGE_BYTES:
                return url, None
            img = Image.open(io.BytesIO(r.content))
            img.load()
            return url, img.convert("RGB")
        except Exception:  # bad URL, timeout, undecodable image: draw a placeholder instead
            return url, None

    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        results = await asyncio.gather(*(one(client, u) for u in urls if u))
    return {url: img for url, img in results if img is not None}


def image_urls(stats: RecapStats, categories: set[Category]) -> set[str]:
    urls: set[str] = set()
    if Category.music in categories:
        urls |= {a.cover_url for a in stats.artists if a.cover_url}
        urls |= {w.cover_url for _, w in stats.songs if w.cover_url}
    if Category.game in categories:
        urls |= {w.cover_url for w, _ in stats.games if w.cover_url}
    if Category.anime in categories:
        urls |= {w.cover_url for _, w in stats.anime if w.cover_url}
    return urls


# ---------- drawing helpers ----------

def _fit(text: str, f: ImageFont.FreeTypeFont, max_width: float) -> str:
    if f.getlength(text) <= max_width:
        return text
    while text and f.getlength(text + "…") > max_width:
        text = text[:-1]
    return text + "…"


def _cover(canvas: Image.Image, img: Image.Image | None, x: int, y: int, w: int, h: int, radius: int = 14) -> None:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    if img is None:
        tile = Image.new("RGBA", (w, h), PLACEHOLDER)
        canvas.alpha_composite(Image.composite(tile, Image.new("RGBA", (w, h)), mask), (x, y))
        return
    canvas.paste(ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS), (x, y), mask)


def _panel(canvas: Image.Image, top: int, height: int) -> None:
    overlay = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(overlay).rounded_rectangle((MARGIN, top, W - MARGIN, top + height), 36, fill=PANEL)
    canvas.alpha_composite(overlay)


def new_canvas(height: int = H) -> Image.Image:
    """Brand background shared by every share card: vertical gradient plus a soft glow."""
    canvas = Image.new("RGBA", (W, height))
    gradient = Image.linear_gradient("L").resize((W, height))
    canvas.paste(Image.composite(Image.new("RGB", (W, height), BG_BOTTOM), Image.new("RGB", (W, height), BG_TOP), gradient))
    glow = Image.new("RGBA", (W, height))
    ImageDraw.Draw(glow).ellipse((W - 380, -320, W + 220, 280), fill=(139, 130, 255, 50))
    canvas.alpha_composite(glow)
    return canvas


def to_jpeg(canvas: Image.Image) -> bytes:
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()


def wrap(text: str, f: ImageFont.FreeTypeFont, max_width: float, max_lines: int) -> list[str]:
    """Greedy character wrap (works for CJK, which has no spaces); last line gets an ellipsis."""
    lines, current = [], ""
    for ch in text:
        if f.getlength(current + ch) <= max_width:
            current += ch
            continue
        lines.append(current)
        current = ch
        if len(lines) == max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)
    elif current and len(lines) == max_lines:
        lines[-1] = _fit(lines[-1] + current, f, max_width)
    return lines


def _hours(minutes: int) -> str:
    h = minutes / 60
    return f"{h:.1f} 小時" if h < 10 else f"{round(h)} 小時"


# ---------- sections: each returns its height, and draws when given a canvas ----------

INNER_W = W - 2 * MARGIN - 2 * PAD


@dataclass(frozen=True)
class Layout:
    """How big to draw. Fewer sections on a card -> larger scale and more items per section."""

    scale: float = 1.0  # multiplies covers and row heights
    items: int = 3  # songs / games listed
    anime_rows: int = 1
    single: bool = False  # the only section on the card: roomier arrangements

    def px(self, value: float) -> int:
        return round(value * self.scale)

    def text(self, size: float) -> int:
        """Text grows less than images: the card can't get wider, so big text would only truncate more."""
        return round(size * min(self.scale, 1.3))

    @property
    def heading(self) -> float:
        return min(self.scale, 1.25)


def _title_h(lay: Layout) -> int:
    return round(74 * lay.heading)


def _title(draw: ImageDraw.ImageDraw, top: int, lay: Layout, text: str, right: str = "") -> int:
    """Draw a section heading; return its height."""
    draw.text((MARGIN + PAD, top + PAD), text, font=font("bold", round(38 * lay.heading)), fill=ACCENT)
    if right:
        f = font("regular", round(30 * lay.heading))
        draw.text((W - MARGIN - PAD - f.getlength(right), top + PAD + round(6 * lay.heading)), right, font=f, fill=MUTED)
    return _title_h(lay)


def _song_rows(canvas, draw, images, lay: Layout, songs, x: int, y: int, row_h: int, row_gap: int) -> None:
    text_w = W - MARGIN - PAD - x - row_h - 18
    title_f, sub_f = font("bold", lay.text(30)), font("regular", lay.text(24))
    for i, (entry, work) in enumerate(songs):
        ry = y + i * (row_h + row_gap)
        _cover(canvas, images.get(work.cover_url), x, ry, row_h, row_h, radius=10)
        tx = x + row_h + 18
        top_pad = (row_h - lay.text(30) - lay.text(24) - lay.text(12)) // 2
        draw.text((tx, ry + top_pad), _fit(work.title, title_f, text_w), font=title_f, fill=WHITE)
        sub = f"{work.creator or ''} · {entry.play_count} 次".lstrip(" ·")
        draw.text((tx, ry + top_pad + lay.text(42)), _fit(sub, sub_f, text_w), font=sub_f, fill=MUTED)


def _music(canvas, top, stats: RecapStats, images, lay: Layout) -> int:
    songs = stats.songs[: lay.items]
    row_h, row_gap = lay.px(74), lay.px(18)
    rows_h = len(songs) * row_h + (len(songs) - 1) * row_gap
    if lay.single:
        # Artist on top, then songs across the full width.
        art = lay.px(220)
        body = art + lay.px(40) + rows_h
    else:
        art = min(lay.px(210), 260)  # keep the song column wide enough for titles
        body = max(art + lay.text(96), rows_h)
    height = PAD + _title_h(lay) + body + PAD
    if canvas is None:
        return height

    draw = ImageDraw.Draw(canvas)
    y = top + PAD + _title(draw, top, lay, f"{stats.period.prefix}最常聽", f"共 {stats.total_plays:,} 次播放")
    x = MARGIN + PAD
    artist = stats.artists[0] if stats.artists else None
    if lay.single:
        if artist:
            _cover(canvas, images.get(artist.cover_url), x, y, art, art, radius=art // 2)
            name_f, plays_f = font("bold", lay.text(52)), font("regular", lay.text(34))
            tx = x + art + 40
            ty = y + (art - lay.text(52) - lay.text(34) - 16) // 2
            draw.text((tx, ty), _fit(artist.name, name_f, W - MARGIN - PAD - tx), font=name_f, fill=WHITE)
            draw.text((tx, ty + lay.text(52) + 16), f"最常聽的歌手 · {artist.plays} 次", font=plays_f, fill=MUTED)
        _song_rows(canvas, draw, images, lay, songs, x, y + art + lay.px(40), row_h, row_gap)
        return height

    if artist:
        name_f, plays_f = font("bold", lay.text(36)), font("regular", lay.text(28))
        _cover(canvas, images.get(artist.cover_url), x, y, art, art, radius=art // 2)
        draw.text((x, y + art + lay.text(14)), _fit(artist.name, name_f, art + 40), font=name_f, fill=WHITE)
        draw.text((x, y + art + lay.text(58)), f"{artist.plays} 次", font=plays_f, fill=MUTED)
    _song_rows(canvas, draw, images, lay, songs, x + art + 44, y, row_h, row_gap)
    return height


def _games(canvas, top, stats: RecapStats, images, lay: Layout) -> int:
    cw, ch, gap = lay.px(64), lay.px(96), lay.px(16)
    rows = stats.games[: lay.items]
    lifetime = stats.period.kind == "all"
    hero_h = lay.text(150) if lifetime else 0
    height = PAD + _title_h(lay) + hero_h + len(rows) * ch + (len(rows) - 1) * gap + PAD
    if canvas is None:
        return height
    draw = ImageDraw.Draw(canvas)
    right = f"{stats.games_count} 款遊戲" if lifetime else f"共 {_hours(stats.games_minutes)}"
    y = top + PAD + _title(draw, top, lay, f"{stats.period.prefix}玩最久", right)
    x = MARGIN + PAD
    if lifetime:
        # The headline number for gamers: total Steam hours, ever.
        total = f"{round(stats.games_minutes / 60):,}"
        num_f, unit_f, cap_f = font("bold", lay.text(84)), font("bold", lay.text(38)), font("regular", lay.text(26))
        draw.text((x, y - lay.text(10)), total, font=num_f, fill=WHITE)
        draw.text((x + num_f.getlength(total) + 14, y + lay.text(36)), "小時", font=unit_f, fill=ACCENT)
        draw.text((x, y + lay.text(92)), "Steam 總遊玩時數", font=cap_f, fill=MUTED)
        y += hero_h
    title_f, hours_f = font("bold", lay.text(32)), font("bold", lay.text(34))
    for i, (work, minutes) in enumerate(rows):
        ry = y + i * (ch + gap)
        _cover(canvas, images.get(work.cover_url), x, ry, cw, ch, radius=10)
        tx = x + cw + 22
        hours = _hours(minutes)
        hw = hours_f.getlength(hours)
        text_y = ry + (ch - lay.text(44)) // 2
        draw.text((tx, text_y), _fit(work.title, title_f, INNER_W - cw - 22 - hw - 24), font=title_f, fill=WHITE)
        draw.text((W - MARGIN - PAD - hw, text_y - lay.text(2)), hours, font=hours_f, fill=ACCENT)
    return height


def _anime(canvas, top, stats: RecapStats, images, lay: Layout) -> int:
    per_row, gap = (3, 28) if lay.single else (4, 20)
    shown = stats.anime[: per_row * lay.anime_rows]
    rows = max(1, -(-len(shown) // per_row))
    cw = (INNER_W - (per_row - 1) * gap) // per_row
    if lay.scale < 1:
        cw = lay.px(cw)  # crowded card: shrink covers too (they start left-aligned)
    # A single row is drawn a bit shorter than 2:3 so three sections fit on one card.
    ch = cw * 4 // 3 if lay.anime_rows == 1 else cw * 3 // 2
    label_f = font("regular", lay.text(26))
    tag_f = font("regular", lay.text(22))
    # Tier sits on the cover (no extra height); the tag gets a line under the title when any exist.
    has_tags = any(getattr(entry, "tag", None) for entry, _ in shown)
    row_h = ch + 12 + lay.text(36) + (lay.text(30) if has_tags else 0)
    height = PAD + _title_h(lay) + rows * row_h + (rows - 1) * gap + PAD
    if canvas is None:
        return height
    draw = ImageDraw.Draw(canvas)
    y = top + PAD + _title(draw, top, lay, "動畫收藏" if stats.period.kind == "all" else f"{stats.period.prefix}新增動畫", f"{stats.anime_count} 部")
    for i, (entry, work) in enumerate(shown):
        x = MARGIN + PAD + (i % per_row) * (cw + gap)
        ry = y + (i // per_row) * (row_h + gap)
        _cover(canvas, images.get(work.cover_url), x, ry, cw, ch)
        tier = getattr(entry, "tier", None)
        if tier in TIER_LABELS:
            _tier_pill(canvas, tier, x + 8, ry + ch - 8, cw - 16, lay)
        draw.text((x, ry + ch + 12), _fit(work.title, label_f, cw), font=label_f, fill=WHITE)
        tag = getattr(entry, "tag", None)
        if tag:
            draw.text((x, ry + ch + 12 + lay.text(36)), _fit(f"#{tag}", tag_f, cw), font=tag_f, fill=ACCENT)
    return height


def _tier_pill(canvas: Image.Image, tier: str, x: int, bottom: int, max_w: int, lay: Layout) -> None:
    """Rounded label in the tier's site color, anchored to the cover's bottom-left corner."""
    f = font("bold", lay.text(22))
    text = TIER_LABELS[tier]
    pad_x, pad_y = lay.text(12), lay.text(6)
    w = min(round(f.getlength(text)) + 2 * pad_x, max_w)
    h = lay.text(22) + 2 * pad_y + 4
    hue, sat = TIER_COLORS[tier]
    r, g, b = colorsys.hls_to_rgb(hue / 360, 0.45, sat / 100)
    overlay = Image.new("RGBA", canvas.size)
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((x, bottom - h, x + w, bottom), h // 2, fill=(round(r * 255), round(g * 255), round(b * 255), 235))
    od.text((x + pad_x, bottom - h + pad_y), _fit(text, f, w - 2 * pad_x), font=f, fill=WHITE)
    canvas.alpha_composite(overlay)


SECTIONS = [(Category.music, _music), (Category.game, _games), (Category.anime, _anime)]
# Below 1.0 only when three sections plus the all-time hours figure need the room.
SCALES = (1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75)


def _layout(chosen, stats: RecapStats, available: int) -> tuple[Layout, list[int]]:
    """Largest layout whose sections fit between header and footer."""
    single = len(chosen) == 1
    items, anime_rows = (5, 2) if single else (3, 1)
    candidates = [Layout(scale, items, anime_rows, single) for scale in SCALES]
    for lay in candidates:
        heights = [fn(None, 0, stats, {}, lay) for _, fn in chosen]
        if sum(heights) + GAP * (len(heights) - 1) <= available:
            return lay, heights
    raise AssertionError("card sections don't fit even at the base layout")


def render_card(
    stats: RecapStats,
    display_name: str,
    footer: str,
    categories: set[Category],
    images: dict[str, Image.Image],
) -> bytes:
    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, 110), "友多聞 YODO Recap", font=font("regular", 34), fill=MUTED)
    draw.text((MARGIN, 158), stats.label, font=font("bold", 92), fill=WHITE)
    draw.text((MARGIN, 276), _fit(display_name, font("regular", 44), W - 2 * MARGIN), font=font("regular", 44), fill=MUTED)

    chosen = [(c, fn) for c, fn in SECTIONS if c in categories and stats.has(c)]
    available = FOOTER_TOP - HEADER_BOTTOM
    lay, heights = _layout(chosen, stats, available)
    total = sum(heights) + GAP * (len(heights) - 1)
    y = HEADER_BOTTOM + max(0, (available - total) // 3)  # spare space mostly below, so content sits near the header
    for (_, fn), h in zip(chosen, heights):
        _panel(canvas, y, h)
        fn(canvas, y, stats, images, lay)
        y += h + GAP

    f = font("regular", 32)
    draw.text(((W - f.getlength(footer)) / 2, FOOTER_TOP + 36), footer, font=f, fill=MUTED)

    return to_jpeg(canvas)
