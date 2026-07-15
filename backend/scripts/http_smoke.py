"""HTTP-level smoke test: register → login → POST /displays/analyze → poll.

Assumes:
  * `uvicorn backend.api.main:app --port 8001` is running.
  * `procrastinate --app=backend.workers.app.app worker` is running.
  * The demo brand + CLIP embeddings have been seeded.
  * The mock display image has been generated.

Run with:
    python -m backend.scripts.http_smoke
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8001"
IMAGE = Path("backend/storage/smoke/mock_display.jpg")


def main() -> int:
    if not IMAGE.exists():
        print(f"[http_smoke] Missing {IMAGE}; run build_mock_display first.")
        return 1

    email = f"http-smoke-{int(time.time())}@example.com"
    password = "correcthorsebattery"

    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        # 1. Register
        r = client.post("/auth/register", json={"email": email, "password": password})
        r.raise_for_status()
        print(f"[http_smoke] Registered user {email} id={r.json()['id']}")

        # 2. Login
        r = client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # 3. Upload
        with IMAGE.open("rb") as fh:
            r = client.post(
                "/displays/analyze",
                headers=auth,
                data={"brand_slug": "demo-brand"},
                files={"image": ("mock_display.jpg", fh, "image/jpeg")},
            )
        r.raise_for_status()
        body = r.json()
        analysis_id = body["analysis"]["id"]
        display_id = body["display"]["id"]
        print(
            f"[http_smoke] Enqueued display={display_id} "
            f"analysis={analysis_id} status={body['analysis']['status']}"
        )

        # 4. Poll (worker picks it up async)
        deadline = time.monotonic() + 120
        last_status = None
        while time.monotonic() < deadline:
            r = client.get(f"/analyses/{analysis_id}", headers=auth)
            r.raise_for_status()
            payload = r.json()
            status = payload["status"]
            if status != last_status:
                print(f"[http_smoke] status={status}")
                last_status = status
            if status in {"complete", "failed"}:
                if status == "failed":
                    print(f"[http_smoke] ERROR: {payload.get('error')}")
                    return 2
                print(f"[http_smoke] prompt_version={payload['prompt_version']}")
                print(f"[http_smoke] model_id      ={payload['model_id']}")
                scene = payload.get("scene_graph") or {}
                products = scene.get("products", [])
                print(f"[http_smoke] products detected: {len(products)}")
                for p in products:
                    sku = p.get("matched_sku") or "-"
                    conf = p.get("matched_confidence")
                    conf_s = f"{conf:.3f}" if conf else " n/a "
                    print(f"    {p.get('label')!r:50} → sku={sku:<14} conf={conf_s}")
                return 0
            time.sleep(2)

    print("[http_smoke] Timed out waiting for analysis to complete.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
