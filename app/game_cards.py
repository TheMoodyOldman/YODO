"""Share cards for the 小遊戲 (1080x1920, same look as the Recap card)."""

import colorsys

from PIL import Image, ImageDraw

from app.card_render import ACCENT, MARGIN, MUTED, W, WHITE, H, _cover, _fit, font, new_canvas, to_jpeg, wrap
from app.games import FREE, PROMPT_BY_KEY, SIZE, Compat
from app.models import CATEGORY_LABELS, User
from app.templating import avatar_hue

FOOTER_Y = H - 74


def _header(draw: ImageDraw.ImageDraw, title: str, subtitle: str | None = None) -> None:
    draw.text((MARGIN, 110), "友多聞 YODO", font=font("regular", 34), fill=MUTED)
    draw.text((MARGIN, 158), title, font=font("bold", 84), fill=WHITE)
    if subtitle:
        draw.text((MARGIN, 268), _fit(subtitle, font("regular", 40), W - 2 * MARGIN), font=font("regular", 40), fill=MUTED)


def _footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    f = font("regular", 32)
    draw.text(((W - f.getlength(text)) / 2, FOOTER_Y), text, font=f, fill=MUTED)


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str, size: int, fill=WHITE, weight: str = "bold") -> None:
    f = font(weight, size)
    draw.text(((W - f.getlength(text)) / 2, y), text, font=f, fill=fill)


def _avatar(canvas: Image.Image, user: User, cx: int, cy: int, r: int) -> None:
    red, green, blue = colorsys.hls_to_rgb(avatar_hue(user.id) / 360, 0.55, 0.7)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(round(red * 255), round(green * 255), round(blue * 255)))
    letter = (user.display_name[:1] or "?").upper()
    f = font("bold", round(r * 1.05))
    box = draw.textbbox((0, 0), letter, font=f)
    draw.text((cx - (box[0] + box[2]) / 2, cy - (box[1] + box[3]) / 2), letter, font=f, fill=WHITE)


def _panel(canvas: Image.Image, box: tuple[int, int, int, int], radius: int = 36) -> None:
    overlay = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius, fill=(255, 255, 255, 24))
    canvas.alpha_composite(overlay)


def render_compat_card(viewer: User, other: User, result: Compat, images: dict, footer: str) -> bytes:
    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    _header(draw, "品味契合度")

    # Two avatars facing each other.
    y = 470
    _avatar(canvas, viewer, W // 2 - 190, y, 110)
    _avatar(canvas, other, W // 2 + 190, y, 110)
    _centered(draw, y - 36, "×", 64, MUTED, "regular")
    name_f = font("bold", 38)
    for cx, user in ((W // 2 - 190, viewer), (W // 2 + 190, other)):
        name = _fit(user.display_name, name_f, 300)
        draw.text((cx - name_f.getlength(name) / 2, y + 128), name, font=name_f, fill=WHITE)

    _centered(draw, 690, f"{result.pct}%", 220)
    _centered(draw, 930, result.label, 64, ACCENT)
    if result.per_category:
        parts = "　".join(f"{CATEGORY_LABELS[c]} {v}%" for c, v in result.per_category.items())
        _centered(draw, 1030, parts, 36, MUTED, "regular")

    if result.shared:
        top = 1120
        shown = result.shared[:4]
        gap, cw = 20, (W - 2 * MARGIN - 80 - 3 * 20) // 4
        ch = cw * 3 // 2
        _panel(canvas, (MARGIN, top, W - MARGIN, top + 110 + ch + 76))  # sized to its content
        draw.text((MARGIN + 40, top + 36), "你們都愛", font=font("bold", 40), fill=ACCENT)
        label_f = font("regular", 26)
        for i, (work, _, _) in enumerate(shown):
            x = MARGIN + 40 + i * (cw + gap)
            _cover(canvas, images.get(work.cover_url), x, top + 110, cw, ch)
            draw.text((x, top + 120 + ch), _fit(work.title, label_f, cw), font=label_f, fill=WHITE)
    _footer(draw, footer)
    return to_jpeg(canvas)


def render_guess_card(user: User, score: int, rounds: int, label: str, footer: str) -> bytes:
    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    _header(draw, "猜猜這是誰的收藏", user.display_name)
    _avatar(canvas, user, W // 2, 620, 150)
    _centered(draw, 860, f"{score} / {rounds}", 230)
    _centered(draw, 1130, label, 72, ACCENT)
    _centered(draw, 1250, f"{rounds} 題猜中 {score} 題", 48, WHITE, "regular")
    _centered(draw, 1340, "你能猜中幾個？", 40, MUTED, "regular")
    _footer(draw, footer)
    return to_jpeg(canvas)


def render_bingo_card(user: User, month: str, board: list[str], marked: list[bool], lines: int, footer: str) -> bytes:
    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    year, mon = month.split("-")
    _header(draw, "興趣賓果", f"{user.display_name} · {year} 年 {int(mon)} 月")

    gap = 12
    cell = (W - 2 * MARGIN - (SIZE - 1) * gap) // SIZE
    top = 380
    text_f = font("bold", 28)
    overlay = Image.new("RGBA", canvas.size)
    od = ImageDraw.Draw(overlay)
    for i, key in enumerate(board):
        r, c = divmod(i, SIZE)
        x, y = MARGIN + c * (cell + gap), top + r * (cell + gap)
        fill = (139, 92, 246, 235) if marked[i] else (255, 255, 255, 26)
        od.rounded_rectangle((x, y, x + cell, y + cell), 22, fill=fill)
    canvas.alpha_composite(overlay)
    for i, key in enumerate(board):
        r, c = divmod(i, SIZE)
        x, y = MARGIN + c * (cell + gap), top + r * (cell + gap)
        text = "FREE" if key == FREE else PROMPT_BY_KEY[key].text
        lines_txt = wrap(text, text_f, cell - 24, 4)
        line_h = 36
        ty = y + (cell - line_h * len(lines_txt)) / 2
        for line in lines_txt:
            draw.text((x + (cell - text_f.getlength(line)) / 2, ty), line, font=text_f, fill=WHITE if marked[i] else MUTED)
            ty += line_h
        if marked[i] and key != FREE:  # small check mark drawn as lines (not every font has ✓)
            draw.line([(x + cell - 40, y + 26), (x + cell - 31, y + 35), (x + cell - 16, y + 16)], fill=WHITE, width=5)

    grid_bottom = top + SIZE * cell + (SIZE - 1) * gap
    _centered(draw, grid_bottom + 70, f"連成 {lines} 條線" if lines else "還沒連成線", 88)
    _centered(draw, grid_bottom + 200, f"{sum(marked) - 1} / {SIZE * SIZE - 1} 格", 44, MUTED, "regular")
    _footer(draw, footer)
    return to_jpeg(canvas)


def render_challenge_card(user: User, kind, chosen: dict, images: dict, footer: str) -> bytes:
    """All 30 days as a 5×6 grid of covers (empty days show their prompt)."""
    from app.challenge import DAYS, PROMPTS, TITLES

    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    _header(draw, TITLES[kind], f"{user.display_name} · 完成 {len(chosen)} / {DAYS} 天")
    cols, gap = 5, 12
    cw = (W - 2 * MARGIN - (cols - 1) * gap) // cols
    ch = cw * 5 // 4
    top = 360
    num_f, prompt_f, title_f = font("bold", 26), font("regular", 22), font("regular", 20)
    for day in range(1, DAYS + 1):
        r, c = divmod(day - 1, cols)
        x, y = MARGIN + c * (cw + gap), top + r * (ch + gap)
        work = chosen.get(day)
        if work:
            _cover(canvas, images.get(work.cover_url), x, y, cw, ch, radius=16)
            shade = Image.new("RGBA", canvas.size)
            sd = ImageDraw.Draw(shade)
            sd.rounded_rectangle((x, y + ch - 46, x + cw, y + ch), 16, fill=(0, 0, 0, 150))
            sd.rounded_rectangle((x + 8, y + 8, x + 58, y + 42), 12, fill=(139, 92, 246, 230))
            canvas.alpha_composite(shade)
            draw.text((x + 10, y + ch - 40), _fit(work.title, title_f, cw - 20), font=title_f, fill=WHITE)
        else:
            _panel(canvas, (x, y, x + cw, y + ch), 16)
            for i, line in enumerate(wrap(PROMPTS[kind][day - 1], prompt_f, cw - 20, 4)):
                draw.text((x + 10, y + 52 + i * 30), line, font=prompt_f, fill=MUTED)
        label = f"{day}"
        draw.text((x + 33 - num_f.getlength(label) / 2, y + 10), label, font=num_f, fill=WHITE)
    _footer(draw, footer)
    return to_jpeg(canvas)


def render_challenge_day_card(user: User, kind, day: int, work, images: dict, footer: str) -> bytes:
    """One day's pick, for daily Stories posts."""
    from app.challenge import DAYS, PROMPTS, TITLES
    from app.models import Category

    canvas = new_canvas()
    draw = ImageDraw.Draw(canvas)
    _header(draw, f"Day {day} / {DAYS}", f"{TITLES[kind]} · {user.display_name}")
    y = 380
    for line in wrap(PROMPTS[kind][day - 1], font("bold", 64), W - 2 * MARGIN, 2):
        _centered(draw, y, line, 64, ACCENT)
        y += 84
    if kind == Category.music:
        cw = ch = 640
    else:
        cw, ch = 540, 810
    top = y + 50
    _cover(canvas, images.get(work.cover_url), (W - cw) // 2, top, cw, ch, radius=28)
    ty = top + ch + 40
    for line in wrap(work.title, font("bold", 52), W - 2 * MARGIN, 2):
        _centered(draw, ty, line, 52)
        ty += 66
    if work.creator:
        _centered(draw, ty + 4, _fit(work.creator, font("regular", 38), W - 2 * MARGIN), 38, MUTED, "regular")
    _footer(draw, footer)
    return to_jpeg(canvas)
