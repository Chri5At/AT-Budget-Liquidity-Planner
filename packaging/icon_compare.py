"""Side-by-side comparison of icon options 1-4 at large + real small sizes.

Shows each candidate big, then at 48/32/24/16 px on a light and a dark strip
(title bar vs. taskbar) so we can judge small-size legibility.

    .venv\\Scripts\\python packaging\\icon_compare.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from icon_options import opt1, opt2, opt3, opt4, _font  # reuse the renderers

HERE = Path(__file__).resolve().parent
OPTS = [("1  Flag stripe + bars", opt1), ("2  Liquidity curve", opt2),
        ("3  Euro coin / tricolor", opt3), ("4  Red euro monogram", opt4)]
SMALL = [48, 32, 24, 16]


def main() -> None:
    big = 240
    gap = 22
    light = (245, 246, 248, 255)
    dark = (33, 41, 54, 255)
    row_h = big + 70
    strip_w = 150
    W = 40 + big + 40 + strip_w + 30 + strip_w + 40
    H = 30 + row_h * len(OPTS)
    sheet = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    ds = ImageDraw.Draw(sheet)
    flbl = _font(24)
    fsmall = _font(15)

    for i, (label, fn) in enumerate(OPTS):
        master = fn()
        y0 = 30 + i * row_h
        ds.text((40, y0 - 4), label, font=flbl, fill=(15, 23, 42, 255), anchor="la")
        ty = y0 + 24
        # big preview
        sheet.alpha_composite(master.resize((big, big), Image.LANCZOS), (40, ty))

        # two strips: light then dark, each with the four small sizes
        for s_i, (bg, name) in enumerate([(light, "Titelleiste"), (dark, "Taskleiste")]):
            sx = 40 + big + 40 + s_i * (strip_w + 30)
            ds.rounded_rectangle((sx, ty, sx + strip_w, ty + big), radius=12, fill=bg)
            txt_col = (90, 100, 115, 255) if s_i == 0 else (200, 208, 220, 255)
            ds.text((sx + strip_w / 2, ty + 8), name, font=fsmall, fill=txt_col, anchor="ma")
            cx = sx + strip_w // 2
            cy = ty + 40
            for sz in SMALL:
                ic = master.resize((sz, sz), Image.LANCZOS)
                sheet.alpha_composite(ic, (int(cx - sz / 2), cy))
                ds.text((cx + 46, cy + sz / 2), f"{sz}px", font=fsmall, fill=txt_col, anchor="lm")
                cy += sz + 14

    sheet.convert("RGB").save(HERE / "compare_1to4.png")
    print("wrote compare_1to4.png")


if __name__ == "__main__":
    main()
