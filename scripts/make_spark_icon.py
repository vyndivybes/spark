"""Generate the SPARK desktop icon (multi-resolution .ico) from code.

Keeps a single source of truth for the app mark so a .lnk, the Electron window
and future packaging all share one asset. Run:
    python scripts/make_spark_icon.py
Output: public/spark.ico (plus public/spark.png for the taskbar preview).
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

# SPARK cockpit palette (see src/index.css + tailwind.config.js).
BG = (11, 18, 32)          # #0b1220 steel-navy cockpit
RING = (6, 182, 212)       # cyan-500
RING_DIM = (22, 78, 99)    # cyan-900
BOLT = (34, 211, 238)      # cyan-400
GOLD = (212, 175, 55)      # champagne accent

SIZE = 1024
SCALE = SIZE / 256.0       # all coords authored on a 256 grid


def _s(v):
    return int(round(v * SCALE))


def build_master() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), BG + (255,))
    d = ImageDraw.Draw(img)

    # Rounded cockpit tile.
    d.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=_s(48), fill=BG + (255,))

    # Outer energy ring.
    pad = _s(22)
    d.ellipse([pad, pad, SIZE - pad, SIZE - pad], outline=RING_DIM + (255,), width=_s(10))
    inner = _s(40)
    d.ellipse([inner, inner, SIZE - inner, SIZE - inner], outline=RING + (255,), width=_s(4))

    # Lightning bolt ("SPARK").
    bolt = [
        (146, 44), (96, 136), (128, 136), (108, 212),
        (168, 112), (134, 112), (156, 44),
    ]
    d.polygon([(_s(x), _s(y)) for x, y in bolt], fill=BOLT + (255,))

    # Champagne-gold core spark.
    cx, cy, r = _s(128), _s(150), _s(14)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD + (255,))
    return img


def main():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    master = build_master()
    png = PUBLIC / "spark.png"
    master.save(png, format="PNG")

    ico = PUBLIC / "spark.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(ico, format="ICO", sizes=sizes)
    print(f"Wrote {png} and {ico} ({ico.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
