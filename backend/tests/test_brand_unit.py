"""Unit tests for brand text chunking, RGB helpers, and understanding score.

These tests do not touch the database or any external provider — they exercise
the pure-Python helpers in `backend.brand.*`.
"""

from __future__ import annotations

from backend.brand import ingestion, rag, understanding
from backend.db.models import Brand, BrandTextKind


# --- Chunking ------------------------------------------------------------

def test_chunk_text_returns_empty_for_blank_input() -> None:
    assert ingestion.chunk_text("") == []
    assert ingestion.chunk_text("   \n\t  ") == []


def test_chunk_text_returns_single_chunk_when_short() -> None:
    text = "This is a short paragraph."
    assert ingestion.chunk_text(text) == [text]


def test_chunk_text_splits_long_text_with_overlap() -> None:
    sentences = [
        "Chunk boundary sentence number {}. It contains distinctive filler "
        "so we can verify overlap behaviour between neighbouring chunks."
        .format(i)
        for i in range(20)
    ]
    text = " ".join(sentences)
    chunks = ingestion.chunk_text(text, target_chars=400, overlap_chars=60)
    assert len(chunks) >= 3
    # Every chunk should stay under 1.5x the target after overlap tails.
    assert all(len(c) <= 600 for c in chunks)
    # Consecutive chunks should share at least some overlap characters.
    for a, b in zip(chunks, chunks[1:]):
        assert any(word in b for word in a[-60:].split() if len(word) > 3)


def test_chunk_text_hard_splits_oversized_sentence() -> None:
    # A single sentence with no punctuation, longer than target.
    text = "word" * 400   # 1600 chars
    chunks = ingestion.chunk_text(text, target_chars=200, overlap_chars=0)
    assert len(chunks) >= 8
    assert all(len(c) <= 200 for c in chunks)


# --- Hex helpers ---------------------------------------------------------

def test_normalise_hex_accepts_short_and_long_forms() -> None:
    assert ingestion._normalise_hex("#abc") == "#AABBCC"
    assert ingestion._normalise_hex("aabbcc") == "#AABBCC"
    assert ingestion._normalise_hex("#AABBCC") == "#AABBCC"


def test_normalise_hex_rejects_invalid() -> None:
    assert ingestion._normalise_hex("") == ""
    assert ingestion._normalise_hex("#zzz") == ""
    assert ingestion._normalise_hex("12345") == ""


def test_hex_to_rgb_roundtrips() -> None:
    assert rag._hex_to_rgb("#000000") == (0, 0, 0)
    assert rag._hex_to_rgb("#ffffff") == (255, 255, 255)
    assert rag._hex_to_rgb("#abc") == (0xAA, 0xBB, 0xCC)
    assert rag._hex_to_rgb("nope") is None


def test_palette_distance_is_symmetric_and_zero_for_identical() -> None:
    a = [(255, 0, 0), (0, 255, 0)]
    b = [(255, 0, 0), (0, 255, 0)]
    assert rag._palette_distance(a, b) == 0.0
    c = [(0, 0, 255)]
    assert rag._palette_distance(a, c) > 0
    assert rag._palette_distance(a, c) == rag._palette_distance(c, a)


def test_keywords_filters_stopwords_and_short_tokens() -> None:
    kws = rag._keywords("The bright terracotta signage on the shelf edge")
    # short + stopwords stripped
    assert "the" not in kws
    assert "on" not in kws
    assert "terracotta" in kws
    assert "signage" in kws
    assert len(kws) <= 5


# --- Understanding score -------------------------------------------------

class _FakeSession:
    """Only implements what `count_text_chunks` / `count_image_chunks` need."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def scalar(self, stmt) -> int:  # noqa: ARG002
        # The tests don't actually inspect the statement — they set the
        # answer per axis on `_counts` and rely on `_stub_counts` below.
        return 0


def _stub_counts(monkeypatch, *, doc: int = 0, do: int = 0, dont: int = 0, images: int = 0):
    def fake_text_count(session, brand_id, kind=None):  # noqa: ARG001
        if kind is None:
            return doc + do + dont
        if kind == BrandTextKind.DOC:
            return doc
        if kind == BrandTextKind.VOICE_DO:
            return do
        if kind == BrandTextKind.VOICE_DONT:
            return dont
        return 0

    def fake_image_count(session, brand_id):  # noqa: ARG001
        return images

    monkeypatch.setattr(understanding, "count_text_chunks", fake_text_count)
    monkeypatch.setattr(understanding, "count_image_chunks", fake_image_count)


def _empty_brand() -> Brand:
    return Brand(id=1, slug="x", name="X")


def test_understanding_score_all_zero_for_empty_brand(monkeypatch) -> None:
    _stub_counts(monkeypatch)
    breakdown = understanding.compute_understanding(_empty_brand(), _FakeSession({}))
    assert breakdown.identity == 0
    assert breakdown.voice == 0
    assert breakdown.docs == 0
    assert breakdown.images == 0
    assert breakdown.audience == 0
    assert breakdown.total == 0


def test_understanding_identity_awards_full_when_profile_populated(monkeypatch) -> None:
    _stub_counts(monkeypatch)
    brand = _empty_brand()
    brand.logo_path = "some/logo.png"
    brand.palette_dominant_hex = ["#111111", "#222222", "#333333"]
    brand.typography = {"display": "Foo", "body": "Bar"}
    breakdown = understanding.compute_understanding(brand, _FakeSession({}))
    assert breakdown.identity == understanding.AXIS_WEIGHTS["identity"]


def test_understanding_voice_uses_paired_minimum(monkeypatch) -> None:
    # 5 dos but only 1 dont → 1 pair → 1/3 of voice weight.
    _stub_counts(monkeypatch, do=5, dont=1)
    breakdown = understanding.compute_understanding(_empty_brand(), _FakeSession({}))
    expected = round(1 / 3 * understanding.AXIS_WEIGHTS["voice"])
    assert breakdown.voice == expected


def test_understanding_total_caps_at_100(monkeypatch) -> None:
    _stub_counts(monkeypatch, doc=50, do=10, dont=10, images=50)
    brand = _empty_brand()
    brand.logo_path = "logo.png"
    brand.palette_dominant_hex = ["#111", "#222", "#333"]
    brand.typography = {"display": "Foo"}
    brand.persona = "A persona."
    brand.competitors = ["A", "B", "C", "D"]
    breakdown = understanding.compute_understanding(brand, _FakeSession({}))
    assert breakdown.total == 100
