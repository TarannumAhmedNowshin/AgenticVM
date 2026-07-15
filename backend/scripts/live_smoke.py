"""Live end-to-end smoke test for Phase 1.

Creates a `Display` + pending `Analysis` pointing at the mock display JPEG,
runs the perception worker task in-process (real Claude vision + real CLIP
matcher), and prints the resulting scene graph.

Requires:
  * Postgres running with `alembic upgrade head` applied.
  * `ANTHROPIC_API_KEY` in `.env`.
  * `[ml]` extra installed (torch + open_clip).
  * `python -m backend.scripts.seed_demo_brand` already run so the demo brand
    catalogue has real CLIP embeddings.

Run with:
    python -m backend.scripts.live_smoke
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.db.models import Analysis, AnalysisStatus, Brand, Display, User
from backend.scripts import seed_demo_brand
from backend.workers.tasks import _run_perception


def main() -> None:
    settings = get_settings()
    image_path = settings.storage_dir / "smoke" / "mock_display.jpg"
    if not image_path.exists():
        raise SystemExit(
            f"Mock display not found at {image_path}. Run "
            "`python -m backend.scripts.build_mock_display` first."
        )

    with SessionLocal() as session:
        brand = session.scalar(
            select(Brand).where(Brand.slug == seed_demo_brand.DEMO_BRAND_SLUG)
        )
        if brand is None:
            raise SystemExit("Demo brand not seeded — run seed_demo_brand first.")

        user = _ensure_smoke_user(session)

        display = Display(
            brand_id=brand.id,
            user_id=user.id,
            image_path=str(image_path),
            image_sha256="smoke" * 12 + "abcd",  # 64 chars
            media_type="image/jpeg",
        )
        session.add(display)
        session.flush()

        analysis = Analysis(display_id=display.id, status=AnalysisStatus.PENDING)
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id
        display_id = display.id

    print(f"[smoke] Created display={display_id}, analysis={analysis_id}")
    print(f"[smoke] Image: {image_path}")
    print("[smoke] Running perception (real Claude + real CLIP) ...")
    started = time.perf_counter()
    asyncio.run(_run_perception(analysis_id))
    elapsed = time.perf_counter() - started
    print(f"[smoke] Task finished in {elapsed:.1f}s")

    with SessionLocal() as session:
        result = session.get(Analysis, analysis_id)
        assert result is not None
        print(f"[smoke] status         = {result.status.value}")
        print(f"[smoke] prompt_version = {result.prompt_version}")
        print(f"[smoke] model_id       = {result.model_id}")
        if result.error:
            print(f"[smoke] error          = {result.error}")
            return

        scene = result.scene_graph or {}
        products = scene.get("products", [])
        text = scene.get("text", [])
        palette = scene.get("palette", {})
        zones = scene.get("zones", {})

        print(f"\n[smoke] products detected: {len(products)}")
        for i, p in enumerate(products, 1):
            match = ""
            if p.get("matched_sku"):
                conf = p.get("matched_confidence")
                match = f"  → SKU {p['matched_sku']} (conf={conf:.3f})" if conf else ""
            print(f"  {i}. {p.get('label')!r} category={p.get('category')}{match}")

        print(f"\n[smoke] text detected: {len(text)}")
        for t in text[:10]:
            print(f"  - {t.get('text')!r}  kind={t.get('kind')}")

        print(f"\n[smoke] palette dominant = {palette.get('dominant_hex')}")
        print(f"[smoke] palette accent   = {palette.get('accent_hex')}")
        print(f"[smoke] focal_points     = {len(zones.get('focal_points', []))}")
        print(f"[smoke] lighting_notes   = {scene.get('lighting_notes')!r}")
        print(f"[smoke] composition_notes= {scene.get('composition_notes')!r}")

        out_path = Path("backend/storage/smoke") / f"scene_{analysis_id}.json"
        out_path.write_text(json.dumps(scene, indent=2), encoding="utf-8")
        print(f"\n[smoke] Full scene graph written to {out_path}")


def _ensure_smoke_user(session) -> User:  # type: ignore[no-untyped-def]
    email = "smoke@example.com"
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, hashed_password="unused-in-smoke", is_active=True)
        session.add(user)
        session.flush()
    return user


if __name__ == "__main__":
    main()
