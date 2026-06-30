"""Generate the application icon: a bold Austrian-red card with a white euro
monogram over faint growth bars — "Austrian budget/liquidity planning".

Renders one high-resolution master and downsamples it (LANCZOS) into a multi-size
Windows .ico. Re-run after any tweak:

    .venv\\Scripts\\python packaging\\make_icon.py

Outputs (next to this script):
    icon.ico            multi-size icon used by the build (--icon)
    icon_preview.png    256px preview for eyeballing the design
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent

# --- palette --------------------------------------------------------------
AUSTRIA_RED = (237, 41, 57, 255)   # #ED2939 — Austrian flag red
RED_DEEP = (201, 28, 45, 255)      # subtle darker red for depth at the bottom
WHITE = (255, 255, 255, 255)
FAINT = (255, 255, 255, 56)        # faint white for the background bars
SHADOW = (8, 20, 33, 70)

S = 1024                            # master render size (square)


def _font(px: int) -> ImageFont.FreeTypeFont:
    for path in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int = S) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = int(size * 0.039)
    card = (m, m, size - m, size - m)
    radius = int(size * 0.205)

    # soft drop shadow
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (card[0], card[1] + int(size * 0.018), card[2], card[3] + int(size * 0.018)),
        radius=radius, fill=SHADOW)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(int(size * 0.012))))

    # rounded card with a subtle vertical red gradient (flat-but-not-lifeless)
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    h = card[3] - card[1]
    for i in range(h):
        t = i / max(1, h - 1)
        col = tuple(int(AUSTRIA_RED[c] + (RED_DEEP[c] - AUSTRIA_RED[c]) * t) for c in range(3))
        gd.line((card[0], card[1] + i, card[2], card[1] + i), fill=col + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(card, radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # faint white ascending bars across the lower half (texture, not focal point)
    bars = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bars)
    base_y = int(card[1] + h * 0.82)
    bw = int(size * 0.105)
    gap = int(size * 0.045)
    x = int(size * 0.205)
    for f in (0.16, 0.24, 0.32, 0.40, 0.48):
        top = base_y - int(h * f)
        bd.rounded_rectangle((x, top, x + bw, base_y), radius=int(bw * 0.3), fill=FAINT)
        x += bw + gap
    img.alpha_composite(Image.composite(bars, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    # white euro monogram — the hero, sized to stay legible down to 16px
    f = _font(int(size * 0.55))
    d.text((size / 2, size / 2 - int(size * 0.035)), "€", font=f, fill=WHITE, anchor="mm")

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
