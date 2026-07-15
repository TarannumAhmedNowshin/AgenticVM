"""CLIP-based product matcher.

Given a `SceneGraph` and the source image, crop each detected product bbox,
embed it with CLIP, and look up the nearest catalogue SKU per brand in
pgvector. Matched SKUs, prices, and categories are written back onto the
`SceneGraph` in place.
"""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.perception.scene_graph import SceneGraph
from backend.db.models import Product
from backend.model_router.router import get_router

_LOG = logging.getLogger(__name__)


def match_scene_products(
    scene: SceneGraph,
    image_bytes: bytes,
    *,
    brand_id: int,
    session: Session,
    min_confidence: float = 0.25,
) -> SceneGraph:
    """Enrich `scene.products` with catalogue matches. Returns the same object."""
    if not scene.products:
        return scene

    with Image.open(BytesIO(image_bytes)) as source:
        source = source.convert("RGB")
        width, height = source.size

        crops: list[Image.Image] = []
        crop_indices: list[int] = []
        for idx, product in enumerate(scene.products):
            crop = _crop_bbox(source, product.bbox, width, height)
            if crop is None:
                continue
            crops.append(crop)
            crop_indices.append(idx)

    if not crops:
        return scene

    router = get_router()
    embeddings = router.clip.embed_pil(crops)

    for idx, embedding in zip(crop_indices, embeddings, strict=True):
        row = _nearest_product(session, brand_id=brand_id, embedding=embedding)
        if row is None:
            continue
        product_row, distance = row
        # pgvector cosine_distance returns 1 - cosine_similarity.
        similarity = 1.0 - float(distance)
        if similarity < min_confidence:
            continue
        detected = scene.products[idx]
        detected.matched_sku = product_row.sku
        detected.matched_confidence = similarity
        if not detected.price and product_row.price:
            detected.price = product_row.price
        if not detected.category and product_row.category:
            detected.category = product_row.category

    return scene


def _crop_bbox(
    source: Image.Image,
    bbox,  # type: ignore[no-untyped-def]
    width: int,
    height: int,
) -> Image.Image | None:
    if bbox is None:
        return None
    left = int(max(0.0, min(1.0, bbox.x)) * width)
    top = int(max(0.0, min(1.0, bbox.y)) * height)
    right = int(max(0.0, min(1.0, bbox.x + bbox.w)) * width)
    bottom = int(max(0.0, min(1.0, bbox.y + bbox.h)) * height)
    if right <= left or bottom <= top:
        return None
    return source.crop((left, top, right, bottom))


def _nearest_product(
    session: Session,
    *,
    brand_id: int,
    embedding: list[float],
) -> tuple[Product, float] | None:
    stmt = (
        select(Product, Product.embedding.cosine_distance(embedding).label("distance"))
        .where(Product.brand_id == brand_id, Product.embedding.is_not(None))
        .order_by("distance")
        .limit(1)
    )
    result = session.execute(stmt).first()
    if result is None:
        return None
    product, distance = result
    return product, float(distance)
