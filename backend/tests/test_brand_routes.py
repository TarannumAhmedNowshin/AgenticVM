"""Integration tests for brand knowledge base routes.

These use the real DB (Postgres from `docker-compose.yml`) and the real
FastAPI app, but mock the CLIP + Azure embedding providers so no external
credentials are required to run the suite.
"""

from __future__ import annotations

import hashlib
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.brand import ingestion, rag


# --- Fakes ---------------------------------------------------------------

class _FakeEmbed:
    """Deterministic 3072-d text embedding driven by SHA-256 of the input."""

    dimensions = 3072
    calls = 0

    async def embed_text(self, inputs: list[str]) -> list[list[float]]:
        type(self).calls += 1
        return [_deterministic_vector(t, 3072) for t in inputs]


class _FakeClip:
    """Deterministic 512-d image embedding driven by SHA-256 of image bytes."""

    dimensions = 512

    def embed_pil(self, images) -> list[list[float]]:  # noqa: ANN001
        vectors: list[list[float]] = []
        for img in images:
            buf = BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            vectors.append(_deterministic_vector(buf.getvalue(), 512))
        return vectors

    def embed_image(self, paths: list[str]) -> list[list[float]]:
        images = [Image.open(p) for p in paths]
        try:
            return self.embed_pil(images)
        finally:
            for img in images:
                img.close()


class _FakeRouter:
    def __init__(self) -> None:
        self.embed = _FakeEmbed()
        self.clip = _FakeClip()


def _deterministic_vector(payload, dims: int) -> list[float]:
    """Repeatable pseudo-random unit vector for tests."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    # Tile the 32-byte digest out to `dims` floats in [-1, 1].
    values: list[float] = []
    while len(values) < dims:
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) >= dims:
                break
        digest = hashlib.sha256(digest).digest()
    # L2-normalise so cosine distances behave sanely.
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


# --- Fixtures ------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_router(monkeypatch: pytest.MonkeyPatch) -> _FakeRouter:
    router = _FakeRouter()
    monkeypatch.setattr(ingestion, "get_router", lambda: router)
    monkeypatch.setattr(rag, "get_router", lambda: router)
    return router


def _register_and_login(client: TestClient) -> str:
    email = f"brands-{int(time.time() * 1000000)}@example.com"
    password = "correcthorsebattery"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _create_brand(client: TestClient, token: str, slug: str) -> dict:
    response = client.post(
        "/brands",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": slug, "name": "Test Brand"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _slug() -> str:
    return f"test-brand-{int(time.time() * 1000000)}"


def _png_bytes(color: tuple[int, int, int] = (200, 150, 100)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (128, 96), color).save(buffer, format="PNG")
    return buffer.getvalue()


# --- Tests ---------------------------------------------------------------

def test_create_brand_and_get_it(client: TestClient) -> None:
    token = _register_and_login(client)
    slug = _slug()
    body = _create_brand(client, token, slug)
    assert body["slug"] == slug
    assert body["name"] == "Test Brand"

    r = client.get(f"/brands/{slug}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["slug"] == slug


def test_create_brand_rejects_duplicate(client: TestClient) -> None:
    token = _register_and_login(client)
    slug = _slug()
    _create_brand(client, token, slug)
    r = client.post(
        "/brands",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": slug, "name": "Duplicate"},
    )
    assert r.status_code == 409


def test_patch_brand_updates_identity(client: TestClient) -> None:
    token = _register_and_login(client)
    slug = _slug()
    _create_brand(client, token, slug)
    r = client.patch(
        f"/brands/{slug}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "palette_dominant_hex": ["#112233", "#aabbcc"],
            "typography": {"display": "Neue", "body": "Serif"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["palette_dominant_hex"] == ["#112233", "#AABBCC"]
    assert body["typography"] == {"display": "Neue", "body": "Serif"}


def test_ingest_text_persists_chunks(client: TestClient) -> None:
    token = _register_and_login(client)
    slug = _slug()
    _create_brand(client, token, slug)
    r = client.post(
        f"/brands/{slug}/assets/text",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Our brand celebrates natural materials, quiet colour, and slow rituals. "
                    "We favour cream, ink, and terracotta. Every product tag is kraft paper.",
            "source": "brand_manifesto.md",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["asset_id"] > 0
    assert body["text_chunks"] >= 1

    # Understanding score should now reflect the doc chunks.
    r = client.get(
        f"/brands/{slug}/understanding",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    breakdown = r.json()["breakdown"]
    assert breakdown["docs"] > 0


def test_voice_persona_competitors_and_retrieval(client: TestClient) -> None:
    token = _register_and_login(client)
    slug = _slug()
    _create_brand(client, token, slug)
    headers = {"Authorization": f"Bearer {token}"}

    # Voice pair
    r = client.post(
        f"/brands/{slug}/voice",
        headers=headers,
        json={
            "do": "Use warm inviting copy that anchors on ritual and craft.",
            "dont": "Avoid urgency spam, all-caps shouty copy, and hype.",
        },
    )
    assert r.status_code == 200
    assert r.json()["text_chunks"] == 2

    # Persona
    r = client.post(
        f"/brands/{slug}/persona",
        headers=headers,
        json={"persona": "Elena, 32, urban creative who values craft over hype."},
    )
    assert r.status_code == 200

    # Competitors
    r = client.post(
        f"/brands/{slug}/competitors",
        headers=headers,
        json={"competitors": ["Everlane", "Kotn", "COS"]},
    )
    assert r.status_code == 200
    assert r.json()["competitors"] == ["Everlane", "Kotn", "COS"]

    # Retrieval should surface at least a text snippet and a voice do/dont.
    r = client.post(
        f"/brands/{slug}/retrieve",
        headers=headers,
        json={"query": "craft ritual urban creative warm copy"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["voice_dos"], "expected voice_do hit"
    assert body["voice_donts"], "expected voice_dont hit"

    # Understanding: identity is still 0 (no logo/palette), but voice + audience count.
    r = client.get(f"/brands/{slug}/understanding", headers=headers)
    breakdown = r.json()["breakdown"]
    assert breakdown["voice"] > 0
    assert breakdown["audience"] > 0


def test_ingest_image_asset_writes_image_chunk_and_awards_identity(
    client: TestClient,
) -> None:
    token = _register_and_login(client)
    slug = _slug()
    _create_brand(client, token, slug)
    headers = {"Authorization": f"Bearer {token}"}

    # Logo — should bump identity score once combined with palette.
    r = client.post(
        f"/brands/{slug}/assets/logo",
        headers=headers,
        files={"file": ("logo.png", _png_bytes((30, 30, 30)), "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["image_chunks"] == 1

    # Reference image
    r = client.post(
        f"/brands/{slug}/assets/image",
        headers=headers,
        files={"file": ("mood.png", _png_bytes((200, 100, 50)), "image/png")},
        data={"caption": "warm sunset moodboard"},
    )
    assert r.status_code == 200

    # Add palette so identity axis can reach full weight.
    r = client.patch(
        f"/brands/{slug}",
        headers=headers,
        json={
            "palette_dominant_hex": ["#F4EBDD", "#1B1A1F", "#B4552C"],
            "typography": {"display": "Foo", "body": "Bar"},
        },
    )
    assert r.status_code == 200

    r = client.get(f"/brands/{slug}/understanding", headers=headers)
    breakdown = r.json()["breakdown"]
    assert breakdown["identity"] == 20  # AXIS_WEIGHTS["identity"]
    assert breakdown["images"] > 0


def test_get_brand_returns_404_for_unknown(client: TestClient) -> None:
    token = _register_and_login(client)
    r = client.get("/brands/does-not-exist", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_ingest_text_requires_auth(client: TestClient) -> None:
    slug = _slug()
    r = client.post(
        f"/brands/{slug}/assets/text",
        json={"text": "hi", "source": "x"},
    )
    assert r.status_code == 401
