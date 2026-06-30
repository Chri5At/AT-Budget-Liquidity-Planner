"""Render several candidate app icons so we can pick a direction.

Each option is an Austria-themed (red-white-red) take on a budget/liquidity app.
Outputs option_1.png … option_6.png plus a contact_sheet.png for comparison.

    .venv\\Scripts\\python packaging\\icon_options.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
S = 1024

RED = (237, 41, 57, 255)      # Austrian flag red
WHITE = (255, 255, 255, 255)
NAVY = (22, 50, 79, 255)
NAVY2 = (37, 74, 110, 255)
TEAL = (13, 148, 136, 255)
TEAL_DK = (15, 118, 110, 255)
GOLD = (214, 158, 24, 255)
SLATE = (71, 85, 105, 255)
INK = (15, 23, 42, 255)


def _font(px: int) -> ImageFont.FreeTypeFont:
    for path in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _base(radius_frac=0.205, margin_frac=0.039):
    """A transparent canvas + draw handle + the rounded-card geometry & mask."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = int(S * margin_frac)
    card = (m, m, S - m, S - m)
    r = int(S * radius_frac)
    # soft drop shadow
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((card[0], card[1] + int(S * 0.018),
                                          card[2], card[3] + int(S * 0.018)),
                                         radius=r, fill=(8, 20, 33, 70))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(int(S * 0.012))))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(card, radius=r, fill=255)
    return img, ImageDraw.Draw(img), card, r, mask


def _paste_clipped(img, layer, mask):
    img.alpha_composite(Image.composite(layer, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))


def _fill_card(d, card, r, color):
    d.rounded_rectangle(card, radius=r, fill=color)


def _bars(d, card, color, fracs, *, baseline=0.74, x0=0.26, bw=0.10, gap=0.045, rounded=True):
    h = card[3] - card[1]
    base_y = int(card[1] + h * baseline)
    bw_px, gap_px = int(S * bw), int(S * gap)
    x = int(S * x0)
    br = int(bw_px * 0.32) if rounded else 0
    for f in fracs:
        top = base_y - int(h * f)
        d.rounded_rectangle((x, top, x + bw_px, base_y), radius=br, fill=color)
        x += bw_px + gap_px


# --- Option 1: navy bars + a red-white-red flag stripe on the left edge -----
def opt1():
    img, d, card, r, mask = _base()
    _fill_card(d, card, r, WHITE)
    # left accent stripe (red / white / red, vertical thirds)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    sw = int((card[2] - card[0]) * 0.14)
    x0, x1 = card[0], card[0] + sw
    h = card[3] - card[1]
    t1 = card[1] + h / 3
    t2 = card[1] + 2 * h / 3
    ld.rectangle((x0, card[1], x1, t1), fill=RED)
    ld.rectangle((x0, t1, x1, t2), fill=WHITE)
    ld.rectangle((x0, t2, x1, card[3]), fill=RED)
    _paste_clipped(img, layer, mask)
    _bars(d, card, NAVY, [0.22, 0.34, 0.46, 0.58, 0.70], x0=0.34, bw=0.095, gap=0.05)
    return img


# --- Option 2: rising liquidity area-curve with a red-white-red base band ----
def opt2():
    img, d, card, r, mask = _base()
    _fill_card(d, card, r, WHITE)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    w = card[2] - card[0]
    h = card[3] - card[1]
    # red-white-red band along the bottom (thin)
    band = int(h * 0.16)
    by0 = card[3] - band
    ld.rectangle((card[0], by0, card[2], by0 + band / 3), fill=RED)
    ld.rectangle((card[0], by0 + 2 * band / 3, card[2], card[3]), fill=RED)
    # area curve above the band
    pts = []
    n = 60
    for i in range(n + 1):
        t = i / n
        x = card[0] + w * (0.10 + 0.80 * t)
        y = by0 - h * (0.10 + 0.46 * (t ** 1.4) + 0.05 * math.sin(t * 6))
        pts.append((x, y))
    poly = pts + [(pts[-1][0], by0), (pts[0][0], by0)]
    ld.polygon(poly, fill=(13, 148, 136, 90))
    ld.line(pts, fill=TEAL_DK, width=int(S * 0.022), joint="curve")
    ex, ey = pts[-1]
    rr = int(S * 0.028)
    ld.ellipse((ex - rr, ey - rr, ex + rr, ey + rr), fill=WHITE, outline=TEAL_DK,
               width=int(S * 0.012))
    _paste_clipped(img, layer, mask)
    return img


# --- Option 3: euro coin centred on the red-white-red tricolor ---------------
def opt3():
    img, d, card, r, mask = _base()
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    h = card[3] - card[1]
    t1, t2 = card[1] + h / 3, card[1] + 2 * h / 3
    ld.rectangle((card[0], card[1], card[2], t1), fill=RED)
    ld.rectangle((card[0], t1, card[2], t2), fill=WHITE)
    ld.rectangle((card[0], t2, card[2], card[3]), fill=RED)
    _paste_clipped(img, layer, mask)
    cx, cy = S / 2, S / 2
    rad = int(S * 0.235)
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=WHITE,
              outline=NAVY, width=int(S * 0.018))
    f = _font(int(S * 0.30))
    d.text((cx, cy - int(S * 0.02)), "€", font=f, fill=NAVY, anchor="mm")
    return img


# --- Option 4: bold red card with a big white euro monogram + faint bars ------
def opt4():
    img, d, card, r, mask = _base()
    _fill_card(d, card, r, RED)
    # faint white ascending bars across the lower third
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _bars(ImageDraw.Draw(layer), card, (255, 255, 255, 60),
          [0.16, 0.24, 0.32, 0.40, 0.48], baseline=0.82, x0=0.20, bw=0.105, gap=0.045)
    _paste_clipped(img, layer, mask)
    f = _font(int(S * 0.46))
    d.text((S / 2, S / 2 - int(S * 0.03)), "€", font=f, fill=WHITE, anchor="mm")
    return img


# --- Option 5: centred bar chart + up-arrow, red-white-red corner ribbon ------
def opt5():
    img, d, card, r, mask = _base()
    _fill_card(d, card, r, WHITE)
    _bars(d, card, NAVY, [0.24, 0.38, 0.30, 0.52], x0=0.30, bw=0.105, gap=0.05, baseline=0.72)
    # up-right arrow
    ax, ay = int(S * 0.70), int(S * 0.34)
    d.line([(int(S * 0.34), int(S * 0.50)), (ax, ay)], fill=TEAL_DK,
           width=int(S * 0.024), joint="curve")
    a = int(S * 0.05)
    d.polygon([(ax + a * 0.4, ay - a * 0.2), (ax - a * 0.5, ay - a * 0.55),
               (ax + a * 0.05, ay + a * 0.6)], fill=TEAL_DK)
    # corner ribbon (top-right): red band with a white centre stripe
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    e = card[2]
    o = int(S * 0.30)
    ld.polygon([(e - o, card[1]), (e, card[1]), (e, card[1] + o)], fill=RED)
    ld.line([(e - o, card[1] + int(S * 0.045)), (e - int(S * 0.045), card[1] + o)],
            fill=WHITE, width=int(S * 0.016))
    _paste_clipped(img, layer, mask)
    return img


# --- Option 6: budget donut split in Austrian red + navy ---------------------
def opt6():
    img, d, card, r, mask = _base()
    _fill_card(d, card, r, WHITE)
    cx, cy = S / 2, S / 2
    rad = int(S * 0.255)
    box = (cx - rad, cy - rad, cx + rad, cy + rad)
    d.pieslice(box, -90, 130, fill=RED)
    d.pieslice(box, 130, 230, fill=NAVY)
    d.pieslice(box, 230, 270, fill=SLATE)
    hole = int(rad * 0.52)
    d.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=WHITE)
    f = _font(int(S * 0.20))
    d.text((cx, cy - int(S * 0.01)), "€", font=f, fill=INK, anchor="mm")
    return img


OPTIONS = [opt1, opt2, opt3, opt4, opt5, opt6]
LABELS = ["1 Flag stripe + bars", "2 Liquidity curve", "3 Euro coin / tricolor",
          "4 Red € monogram", "5 Bars + arrow + ribbon", "6 Budget donut"]


def main() -> None:
    previews = []
    for i, fn in enumerate(OPTIONS, 1):
        im = fn().resize((256, 256), Image.LANCZOS)
        im.save(HERE / f"option_{i}.png")
        previews.append(im)

    # contact sheet: 3 columns x 2 rows with labels
    cell, pad, lbl = 256, 26, 34
    cols, rows = 3, 2
    W = cols * cell + (cols + 1) * pad
    Hgt = rows * (cell + lbl) + (rows + 1) * pad
    sheet = Image.new("RGBA", (W, Hgt), (245, 246, 248, 255))
    ds = ImageDraw.Draw(sheet)
    f = _font(22)
    for idx, im in enumerate(previews):
        c, rrow = idx % cols, idx // cols
        x = pad + c * (cell + pad)
        y = pad + rrow * (cell + lbl + pad)
        sheet.alpha_composite(im, (x, y))
        ds.text((x + cell / 2, y + cell + 6), LABELS[idx], font=f, fill=(30, 41, 59, 255),
                anchor="ma")
    sheet.convert("RGB").save(HERE / "contact_sheet.png")
    print("wrote option_1..6.png and contact_sheet.png")


if __name__ == "__main__":
    main()
