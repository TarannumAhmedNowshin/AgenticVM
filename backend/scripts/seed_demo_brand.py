"""Seed a demo brand + ~30 synthetic products with CLIP embeddings.

Idempotent: re-running updates the existing rows in place. Requires:
  * Postgres running (docker compose up -d)
  * `alembic upgrade head` applied (brands + products tables)
  * The `[ml]` extra installed for CLIP embeddings — otherwise embeddings
    are skipped and the matcher will simply return no matches.

Product images are procedurally-drawn category silhouettes (t-shirt, bottle,
shoe, etc.) with per-SKU colour variation. This gives CLIP enough visual
signal to produce categorically-separable embeddings, unlike solid-colour
tiles.

Run with:
    python -m backend.scripts.seed_demo_brand
"""

from __future__ import annotations

import colorsys
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import select

from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import Brand, Product

_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.StreamHandler())
_LOG.setLevel(logging.INFO)

DEMO_BRAND_SLUG = "demo-brand"
CANVAS_SIZE = (512, 512)
BACKGROUND = (245, 244, 240)  # off-white studio background


@dataclass(frozen=True)
class SeedProduct:
    sku: str
    title: str
    category: str
    price: str


# 30 synthetic SKUs spread across a few categories so the matcher has variety.
_SEED_PRODUCTS: list[SeedProduct] = [
    SeedProduct("APP-TSH-001", "Classic Cotton Tee — White", "apparel/tops", "$24"),
    SeedProduct("APP-TSH-002", "Classic Cotton Tee — Black", "apparel/tops", "$24"),
    SeedProduct("APP-TSH-003", "Graphic Tee — Sunset", "apparel/tops", "$32"),
    SeedProduct("APP-JKT-004", "Denim Trucker Jacket", "apparel/outerwear", "$120"),
    SeedProduct("APP-JKT-005", "Puffer Jacket — Olive", "apparel/outerwear", "$180"),
    SeedProduct("APP-JNS-006", "Slim Fit Jeans — Indigo", "apparel/bottoms", "$85"),
    SeedProduct("APP-JNS-007", "Straight Leg Jeans — Black", "apparel/bottoms", "$85"),
    SeedProduct("APP-SHR-008", "Cargo Shorts — Khaki", "apparel/bottoms", "$55"),
    SeedProduct("APP-DRS-009", "Wrap Dress — Floral", "apparel/dresses", "$95"),
    SeedProduct("APP-DRS-010", "Linen Sundress — Cream", "apparel/dresses", "$110"),
    SeedProduct("ACC-BAG-011", "Canvas Tote — Natural", "accessories/bags", "$40"),
    SeedProduct("ACC-BAG-012", "Leather Crossbody — Tan", "accessories/bags", "$150"),
    SeedProduct("ACC-HAT-013", "Wide Brim Straw Hat", "accessories/hats", "$45"),
    SeedProduct("ACC-HAT-014", "Baseball Cap — Navy", "accessories/hats", "$28"),
    SeedProduct("ACC-BLT-015", "Woven Belt — Cognac", "accessories/belts", "$60"),
    SeedProduct("FTW-SNK-016", "Low-Top Sneakers — White", "footwear/sneakers", "$95"),
    SeedProduct("FTW-SNK-017", "Chunky Runner — Grey", "footwear/sneakers", "$130"),
    SeedProduct("FTW-BOT-018", "Chelsea Boots — Black", "footwear/boots", "$180"),
    SeedProduct("FTW-SND-019", "Slide Sandal — Tan", "footwear/sandals", "$50"),
    SeedProduct("BTY-LIP-020", "Matte Lipstick — Rosewood", "beauty/lips", "$22"),
    SeedProduct("BTY-LIP-021", "Lip Gloss — Peach Shimmer", "beauty/lips", "$18"),
    SeedProduct("BTY-FRG-022", "Eau de Parfum — Amber", "beauty/fragrance", "$85"),
    SeedProduct("BTY-SKN-023", "Hydrating Serum 30ml", "beauty/skincare", "$48"),
    SeedProduct("BTY-SKN-024", "SPF 50 Sunscreen 50ml", "beauty/skincare", "$32"),
    SeedProduct("HOM-CAN-025", "Soy Candle — Fig & Cedar", "home/candles", "$36"),
    SeedProduct("HOM-CAN-026", "Soy Candle — Sea Salt", "home/candles", "$36"),
    SeedProduct("HOM-MUG-027", "Stoneware Mug — Speckled", "home/kitchen", "$18"),
    SeedProduct("HOM-THR-028", "Chunky Knit Throw — Oat", "home/textiles", "$110"),
    SeedProduct("TCH-HDP-029", "Wireless Headphones — Sand", "tech/audio", "$180"),
    SeedProduct("TCH-BTL-030", "Insulated Bottle 750ml", "tech/lifestyle", "$40"),
]


def main() -> None:
    settings = get_settings()
    seed_dir = settings.storage_dir / "seed" / DEMO_BRAND_SLUG
    seed_dir.mkdir(parents=True, exist_ok=True)

    image_paths = _generate_placeholder_images(seed_dir, _SEED_PRODUCTS)
    embeddings = _try_embed(image_paths)

    with SessionLocal() as session:
        brand = _upsert_brand(session)
        _upsert_products(session, brand, image_paths, embeddings)
        session.commit()

    _LOG.info(
        "Seeded brand '%s' with %d products (%s embeddings).",
        DEMO_BRAND_SLUG,
        len(_SEED_PRODUCTS),
        "with" if embeddings else "without",
    )


def _upsert_brand(session) -> Brand:
    brand = session.scalar(select(Brand).where(Brand.slug == DEMO_BRAND_SLUG))
    if brand is None:
        brand = Brand(
            slug=DEMO_BRAND_SLUG,
            name="Demo Brand Co.",
            voice=(
                "Warm, confident, and playful. Speaks to design-minded 25–40 "
                "year olds who value craft over hype."
            ),
            guardrails=(
                "Never discount below 15%. Never use flame or firearm imagery. "
                "Palette anchors on cream, ink, and terracotta."
            ),
        )
        session.add(brand)
        session.flush()
    return brand


def _upsert_products(
    session,
    brand: Brand,
    image_paths: dict[str, Path],
    embeddings: dict[str, list[float]] | None,
) -> None:
    existing = {
        p.sku: p
        for p in session.scalars(select(Product).where(Product.brand_id == brand.id)).all()
    }
    for seed in _SEED_PRODUCTS:
        image_path = str(image_paths[seed.sku])
        embedding = embeddings.get(seed.sku) if embeddings else None
        product = existing.get(seed.sku)
        if product is None:
            product = Product(
                brand_id=brand.id,
                sku=seed.sku,
                title=seed.title,
                category=seed.category,
                price=seed.price,
                image_path=image_path,
                embedding=embedding,
            )
            session.add(product)
        else:
            product.title = seed.title
            product.category = seed.category
            product.price = seed.price
            product.image_path = image_path
            if embedding is not None:
                product.embedding = embedding


def _generate_placeholder_images(
    seed_dir: Path, products: list[SeedProduct]
) -> dict[str, Path]:
    """Draw one category-specific silhouette per SKU with hash-based colour variation.

    Always re-renders so bumping the rendering code takes effect on re-seed.
    """
    paths: dict[str, Path] = {}
    for seed in products:
        path = seed_dir / f"{seed.sku}.png"
        _render_product_tile(path, seed)
        paths[seed.sku] = path
    return paths


# --- silhouette rendering -------------------------------------------------

def _render_product_tile(path: Path, seed: SeedProduct) -> None:
    image = Image.new("RGB", CANVAS_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    primary, secondary = _palette_for(seed.sku)
    kind = _shape_kind(seed.category)
    _SHAPE_RENDERERS[kind](draw, primary, secondary)
    image.save(path, format="PNG")


def _palette_for(sku: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Deterministic (primary, secondary) RGB pair per SKU, well-separated in hue."""
    digest = hashlib.sha256(sku.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    sat = 0.35 + (digest[1] / 255.0) * 0.5
    val = 0.55 + (digest[2] / 255.0) * 0.35
    primary = _hsv_to_rgb(hue, sat, val)
    secondary = _hsv_to_rgb((hue + 0.5) % 1.0, min(1.0, sat + 0.15), max(0.2, val - 0.25))
    return primary, secondary


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _shape_kind(category: str | None) -> str:
    if not category:
        return "generic"
    for prefix, kind in _CATEGORY_TO_SHAPE:
        if category.startswith(prefix):
            return kind
    return "generic"


# Order matters: match most-specific prefix first.
_CATEGORY_TO_SHAPE: list[tuple[str, str]] = [
    ("apparel/tops", "shirt"),
    ("apparel/outerwear", "jacket"),
    ("apparel/bottoms", "pants"),
    ("apparel/dresses", "dress"),
    ("accessories/bags", "bag"),
    ("accessories/hats", "hat"),
    ("accessories/belts", "belt"),
    ("footwear/sneakers", "shoe"),
    ("footwear/boots", "boot"),
    ("footwear/sandals", "sandal"),
    ("beauty/lips", "lipstick"),
    ("beauty/fragrance", "perfume"),
    ("beauty/skincare", "pump_bottle"),
    ("home/candles", "candle"),
    ("home/kitchen", "mug"),
    ("home/textiles", "blanket"),
    ("tech/audio", "headphones"),
    ("tech/lifestyle", "water_bottle"),
]


def _shirt(d: ImageDraw.ImageDraw, p, s) -> None:  # type: ignore[no-untyped-def]
    # T-shirt: hexagonal body + two sleeve wings.
    d.polygon(
        [(160, 150), (200, 120), (312, 120), (352, 150), (400, 200), (360, 240),
         (330, 220), (330, 400), (182, 400), (182, 220), (152, 240), (112, 200)],
        fill=p,
        outline=s,
        width=3,
    )
    d.ellipse((236, 118, 276, 148), fill=BACKGROUND, outline=s, width=2)


def _jacket(d, p, s) -> None:  # type: ignore[no-untyped-def]
    _shirt(d, p, s)
    # Zipper down the centre + pocket lines.
    d.line((256, 148, 256, 400), fill=s, width=4)
    d.rectangle((200, 300, 240, 340), outline=s, width=3)
    d.rectangle((272, 300, 312, 340), outline=s, width=3)


def _pants(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.polygon(
        [(180, 110), (332, 110), (352, 400), (280, 400), (256, 200),
         (232, 400), (160, 400)],
        fill=p,
        outline=s,
        width=3,
    )
    d.line((180, 130, 332, 130), fill=s, width=3)  # waistband


def _dress(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.polygon(
        [(216, 120), (296, 120), (336, 180), (400, 420), (112, 420), (176, 180)],
        fill=p,
        outline=s,
        width=3,
    )
    d.line((216, 180, 296, 180), fill=s, width=3)  # waistline


def _bag(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((140, 200, 372, 400), fill=p, outline=s, width=3)
    d.arc((180, 100, 332, 260), start=180, end=360, fill=s, width=6)  # handle
    d.rectangle((240, 260, 272, 300), fill=s)  # clasp


def _hat(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.ellipse((100, 280, 412, 340), fill=p, outline=s, width=3)  # brim
    d.pieslice((160, 140, 352, 320), start=180, end=360, fill=p, outline=s, width=3)
    d.rectangle((160, 280, 352, 300), fill=s)  # band


def _belt(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((60, 240, 452, 280), fill=p, outline=s, width=3)
    d.rectangle((216, 220, 296, 300), outline=s, width=4)  # buckle
    for x in range(90, 450, 40):
        d.ellipse((x, 254, x + 8, 266), fill=s)  # stitch holes


def _shoe(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.polygon(
        [(80, 340), (140, 260), (240, 240), (340, 260), (420, 300), (420, 360), (80, 380)],
        fill=p,
        outline=s,
        width=3,
    )
    d.rectangle((80, 360, 420, 400), fill=s)  # sole
    d.line((140, 300, 340, 300), fill=s, width=3)  # laces area


def _boot(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.polygon(
        [(160, 120), (280, 120), (300, 320), (420, 320), (420, 400), (160, 400)],
        fill=p,
        outline=s,
        width=3,
    )
    d.rectangle((160, 380, 420, 410), fill=s)


def _sandal(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.ellipse((80, 280, 432, 360), fill=p, outline=s, width=3)  # sole
    d.line((256, 300, 180, 200), fill=s, width=8)  # strap
    d.line((256, 300, 332, 200), fill=s, width=8)


def _lipstick(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((216, 260, 296, 420), fill=s, outline=(20, 20, 20), width=3)  # base
    d.rectangle((228, 160, 284, 260), fill=p, outline=(20, 20, 20), width=3)  # bullet holder
    d.polygon([(228, 160), (284, 160), (256, 100)], fill=p, outline=(20, 20, 20), width=2)


def _perfume(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((180, 200, 332, 420), fill=p, outline=s, width=3)  # bottle
    d.rectangle((220, 140, 292, 200), fill=s)  # neck
    d.rectangle((208, 100, 304, 140), fill=s, outline=(30, 30, 30), width=2)  # cap


def _pump_bottle(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((200, 200, 312, 420), fill=p, outline=s, width=3)
    d.rectangle((240, 130, 272, 200), fill=s)  # neck
    d.rectangle((216, 100, 296, 130), fill=s, outline=(30, 30, 30), width=2)  # pump head
    d.rectangle((296, 105, 340, 120), fill=s)  # nozzle


def _candle(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((180, 180, 332, 420), fill=p, outline=s, width=3)  # jar
    d.line((180, 220, 332, 220), fill=s, width=2)  # label top
    d.line((180, 320, 332, 320), fill=s, width=2)  # label bottom
    d.line((256, 160, 256, 190), fill=(40, 40, 40), width=3)  # wick


def _mug(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((180, 180, 320, 380), fill=p, outline=s, width=3)
    d.arc((300, 220, 400, 340), start=270, end=90, fill=s, width=8)  # handle
    d.ellipse((180, 160, 320, 200), fill=p, outline=s, width=3)  # rim


def _blanket(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((100, 160, 412, 400), fill=p, outline=s, width=3)
    for y in range(180, 400, 30):
        d.line((100, y, 412, y), fill=s, width=2)  # knit lines
    d.polygon([(100, 400), (140, 420), (100, 420)], fill=s)  # corner fold


def _headphones(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.arc((120, 120, 392, 360), start=180, end=360, fill=s, width=10)  # headband
    d.ellipse((100, 260, 200, 380), fill=p, outline=s, width=3)  # left cup
    d.ellipse((312, 260, 412, 380), fill=p, outline=s, width=3)  # right cup


def _water_bottle(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((200, 180, 312, 420), fill=p, outline=s, width=3)
    d.rectangle((228, 120, 284, 180), fill=p, outline=s, width=3)  # neck
    d.rectangle((220, 100, 292, 130), fill=s)  # cap
    d.line((200, 260, 312, 260), fill=s, width=2)  # measurement line
    d.line((200, 340, 312, 340), fill=s, width=2)


def _generic(d, p, s) -> None:  # type: ignore[no-untyped-def]
    d.rectangle((140, 140, 372, 372), fill=p, outline=s, width=3)
    d.line((140, 140, 372, 372), fill=s, width=3)


_SHAPE_RENDERERS = {
    "shirt": _shirt,
    "jacket": _jacket,
    "pants": _pants,
    "dress": _dress,
    "bag": _bag,
    "hat": _hat,
    "belt": _belt,
    "shoe": _shoe,
    "boot": _boot,
    "sandal": _sandal,
    "lipstick": _lipstick,
    "perfume": _perfume,
    "pump_bottle": _pump_bottle,
    "candle": _candle,
    "mug": _mug,
    "blanket": _blanket,
    "headphones": _headphones,
    "water_bottle": _water_bottle,
    "generic": _generic,
}


def _try_embed(image_paths: dict[str, Path]) -> dict[str, list[float]] | None:
    """Embed all product images with CLIP, or return None if the [ml] extra is missing."""
    try:
        from backend.model_router.router import get_router

        clip = get_router().clip
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("CLIP unavailable, skipping embeddings: %s", exc)
        return None

    skus = list(image_paths.keys())
    vectors = clip.embed_image([str(image_paths[s]) for s in skus])
    return dict(zip(skus, vectors, strict=True))


if __name__ == "__main__":
    main()

