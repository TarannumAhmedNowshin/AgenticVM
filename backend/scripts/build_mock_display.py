"""One-shot helper to build a mock retail-display photo for smoke tests.

Assembles a shelf-like composite from a handful of seed product silhouettes,
adds a floor / wall gradient, a signage banner, and a price tag or two.
Not intended to be pretty — just visually structured enough that Claude
vision can produce a non-trivial SceneGraph and CLIP has something to match
against.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from backend.config import get_settings

CANVAS = (1280, 960)
WALL_TOP = (232, 218, 200)
WALL_BOTTOM = (198, 182, 160)
SHELF_COLOUR = (110, 82, 56)


def build_mock_display() -> Path:
    settings = get_settings()
    canvas = Image.new("RGB", CANVAS, (240, 235, 225))
    _paint_wall(canvas)
    _paint_shelf(canvas)
    _place_products(canvas)
    _paint_signage(canvas)
    _paint_price_tag(canvas)

    output_dir = settings.storage_dir / "smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "mock_display.jpg"
    canvas.save(path, format="JPEG", quality=90)
    return path


def _paint_wall(canvas: Image.Image) -> None:
    W, H = canvas.size
    for y in range(H):
        t = y / H
        r = int(WALL_TOP[0] * (1 - t) + WALL_BOTTOM[0] * t)
        g = int(WALL_TOP[1] * (1 - t) + WALL_BOTTOM[1] * t)
        b = int(WALL_TOP[2] * (1 - t) + WALL_BOTTOM[2] * t)
        ImageDraw.Draw(canvas).line((0, y, W, y), fill=(r, g, b))


def _paint_shelf(canvas: Image.Image) -> None:
    d = ImageDraw.Draw(canvas)
    d.rectangle((60, 640, 1220, 700), fill=SHELF_COLOUR, outline=(60, 40, 20), width=3)
    d.rectangle((60, 700, 1220, 780), fill=(70, 52, 34))
    # Front lip highlight.
    d.line((60, 645, 1220, 645), fill=(150, 120, 90), width=2)


def _place_products(canvas: Image.Image) -> None:
    """Paste seed silhouettes onto the shelf, sized to fit."""
    settings = get_settings()
    seed_dir = settings.storage_dir / "seed" / "demo-brand"
    # Pick a mix of visually distinct categories.
    picks = [
        ("APP-TSH-001.png", (80, 380), 240),
        ("HOM-MUG-027.png", (360, 460), 200),
        ("BTY-FRG-022.png", (620, 380), 240),
        ("FTW-SNK-016.png", (880, 460), 240),
        ("TCH-HDP-029.png", (1080, 400), 220),
    ]
    for filename, (x, y), size in picks:
        product_path = seed_dir / filename
        if not product_path.exists():
            continue
        product = Image.open(product_path).convert("RGB").resize((size, size), Image.LANCZOS)
        # Soft shadow.
        shadow = Image.new("RGBA", (size + 40, 24), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse(
            (0, 0, size + 40, 24), fill=(0, 0, 0, 110)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        canvas.paste(shadow, (x - 20, y + size - 12), shadow)
        canvas.paste(product, (x, y))


def _paint_signage(canvas: Image.Image) -> None:
    d = ImageDraw.Draw(canvas)
    # Banner across the top.
    d.rectangle((160, 80, 1120, 200), fill=(20, 40, 80), outline=(240, 220, 180), width=4)
    _draw_text_centered(d, "SUMMER ESSENTIALS", (640, 120), size=54, fill=(255, 240, 200))
    _draw_text_centered(d, "up to 30% off select styles", (640, 170), size=26, fill=(220, 210, 190))


def _paint_price_tag(canvas: Image.Image) -> None:
    d = ImageDraw.Draw(canvas)
    d.polygon(
        [(940, 720), (1120, 720), (1140, 780), (1120, 840), (940, 840), (920, 780)],
        fill=(220, 60, 60),
        outline=(120, 20, 20),
        width=3,
    )
    _draw_text_centered(d, "$45", (1030, 760), size=42, fill=(255, 255, 255))
    _draw_text_centered(d, "TODAY", (1030, 810), size=20, fill=(255, 220, 200))


def _draw_text_centered(
    d: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    size: int,
    fill: tuple[int, int, int],
) -> None:
    # PIL's default font is bitmap and doesn't scale, so fake weight with
    # stroke_width — good enough for a smoke-test image.
    d.text(
        center,
        text,
        fill=fill,
        anchor="mm",
        stroke_width=max(1, size // 20),
        stroke_fill=fill,
    )


if __name__ == "__main__":
    path = build_mock_display()
    with Image.open(path) as img:
        print(f"Wrote {path} ({img.width}x{img.height}, {path.stat().st_size} bytes)")
