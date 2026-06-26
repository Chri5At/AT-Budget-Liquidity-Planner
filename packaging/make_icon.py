"""Generate the application icon: an Austrian (red-white-red) card with an
ascending bar chart + rising trend line — i.e. "Austrian budget/liquidity planning".

Renders a single high-resolution master and downsamples it (LANCZOS) into a
multi-size Windows .ico. Re-run after any tweak:

    .venv\\Scripts\\python packaging\\make_icon.py

Outputs (next to this script):
    icon.ico            multi-size icon used by the build (--icon)
    icon_preview.png    256px preview for eyeballing the design
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

# --- palette --------------------------------------------------------------
AUSTRIA_RED = (237, 41, 57, 255)   # #ED2939 — Austrian flag red
WHITE = (255, 255, 255, 255)
NAVY = (21, 50, 79, 255)           # #15324F — chart bars (finance)
NAVY_DARK = (13, 33, 53, 255)
SHADOW = (8, 20, 33, 60)

S = 1024                            # master render size (square)


def _rr(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(size: int = S) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = int(size * 0.039)                  # outer margin
    card = (m, m, size - m, size - m)
    radius = int(size * 0.205)
    h = card[3] - card[1]
    third = h / 3.0
    top_b = card[1] + third
    bot_b = card[1] + 2 * third

    # Soft drop shadow under the card.
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (card[0], card[1] + int(size * 0.02), card[2], card[3] + int(size * 0.02)),
        radius=radius, fill=SHADOW)
    img.alpha_composite(sh)

    # --- Austrian tricolor card (red / white / red), drawn via a rounded mask ---
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(card, radius=radius, fill=255)
    bands = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bands)
    bd.rectangle((card[0], card[1], card[2], top_b), fill=AUSTRIA_RED)
    bd.rectangle((card[0], top_b, card[2], bot_b), fill=WHITE)
    bd.rectangle((card[0], bot_b, card[2], card[3]), fill=AUSTRIA_RED)
    img.paste(bands, (0, 0), mask)

    # --- ascending bar chart ---------------------------------------------
    base_y = int(card[1] + h * 0.70)       # baseline near lower third
    x0 = int(size * 0.255)
    bar_w = int(size * 0.082)
    gap = int(size * 0.043)
    # heights as a fraction of card height; the tallest crosses into the top band
    fracs = [0.20, 0.30, 0.41, 0.52, 0.63]
    br = int(bar_w * 0.30)                  # bar corner radius
    centers = []
    for i, f in enumerate(fracs):
        x = x0 + i * (bar_w + gap)
        top = base_y - int(h * f)
        # white halo so navy bars stay legible where they cross the red band
        _rr(d, (x - 6, top - 6, x + bar_w + 6, base_y), br + 4, WHITE)
        _rr(d, (x, top, x + bar_w, base_y), br, NAVY if i % 2 else NAVY_DARK)
        centers.append((x + bar_w / 2, top))

    # --- rising trend line + arrowhead (Austrian red accent) --------------
    off = int(size * 0.012)
    pts = [(cx, cy - off) for cx, cy in centers]
    # continue the line past the last bar into open space so the arrow is clear
    tip = (centers[-1][0] + bar_w * 1.05, centers[-1][1] - off - int(h * 0.085))
    line_pts = pts + [tip]
    # white underlay for contrast, then the red line on top
    d.line(line_pts, fill=WHITE, width=int(size * 0.036), joint="curve")
    d.line(line_pts, fill=AUSTRIA_RED, width=int(size * 0.022), joint="curve")
    # data-point nodes on the bars
    for cx, cy in pts:
        rr = int(size * 0.016)
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=WHITE, outline=AUSTRIA_RED,
                  width=int(size * 0.009))
    # clean arrowhead at the tip, aligned with the final segment direction
    import math
    px, py = pts[-1]
    ang = math.atan2(tip[1] - py, tip[0] - px)
    a = int(size * 0.060)
    left = (tip[0] + a * math.cos(ang + 2.5), tip[1] + a * math.sin(ang + 2.5))
    right = (tip[0] + a * math.cos(ang - 2.5), tip[1] + a * math.sin(ang - 2.5))
    d.polygon([tip, left, right], fill=AUSTRIA_RED)

    return img


def main() -> None:
    master = render(S)
    master.resize((256, 256), Image.LANCZOS).save(HERE / "icon_preview.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [master.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(HERE / "icon.ico", format="ICO",
                    sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    print(f"wrote {HERE / 'icon.ico'} and icon_preview.png")


if __name__ == "__main__":
    main()
