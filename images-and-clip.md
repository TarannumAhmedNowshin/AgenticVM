# How images & CLIP work in AVMS

A quick reference for **what images exist in this project, where they come from, and what CLIP is doing with them**. Written after the Phase 1 live end-to-end verification (see [progress.md](progress.md)).

---

## 1. Two kinds of "images" in the pipeline

There are two totally different image streams. Don't mix them up:

| Kind | What it is | Where it comes from | Where it lives |
|---|---|---|---|
| **Brand catalogue images** | The reference photos of each product a brand sells | Uploaded by the brand (production) / procedurally drawn (dev) | `backend/storage/seed/<brand-slug>/*.png`, embedded into `products.embedding` (pgvector 512-d) |
| **Display photos** | The in-store shelf photo a user snaps and analyses | Uploaded via `POST /displays/analyze` (production) / drawn with Pillow (smoke tests) | `backend/storage/displays/<brand-slug>/*.jpg` |

**No AI image generation runs in Phase 1.** Both streams are just pixels the pipeline reads.

Image *generation* enters in Phase 4 (`Gemini image editor + Cloudflare fallback`) when we render the re-merchandised mockup. That path is stubbed but not wired up yet.

---

## 2. How we "build" the demo images

Both demo scripts use Pillow (`PIL`) primitives — polygons, rectangles, gradients. No models, no APIs.

### 2.1 Seed catalogue — `backend/scripts/seed_demo_brand.py`

- Inserts one demo brand + 30 SKUs across apparel / accessories / footwear / beauty / home / tech.
- For each SKU, renders a **category-specific silhouette** on a 512×512 off-white canvas:
  t-shirt (hexagonal body + sleeves), pants, dress, jacket, bag, hat, belt, sneaker, boot, sandal, lipstick, perfume bottle, pump bottle, candle, mug, blanket, headphones, water bottle.
- Colours are deterministic per SKU: `sha256(sku)` → HSV hue+saturation+value → RGB. A complementary secondary colour comes from the same hash. That guarantees:
  1. **Re-running the seed produces the exact same images** (idempotent).
  2. Every SKU is **visually distinct** but the category shape stays consistent, so CLIP produces categorically-separable embeddings.
- Each rendered PNG is embedded with CLIP, and the 512-d vector is written to `products.embedding`.

Why silhouettes and not solid colour tiles? Solid tiles all collapse to nearly the same CLIP vector — the matcher becomes useless. Category shapes give CLIP enough visual signal to actually cluster.

### 2.2 Mock display — `backend/scripts/build_mock_display.py`

- Composes a fake shop-shelf JPEG for smoke tests: 1280×960 canvas, wall gradient, brown "shelf" rectangle, 5 product silhouettes lifted from the seed renderers (t-shirt, mug, perfume, sneaker, headphones), a navy signage banner, a red `TODAY $45` price tag.
- Saved to `backend/storage/smoke/mock_display.jpg` (~63 KB).
- The backend has no idea this JPEG was drawn programmatically — it's just bytes coming in through the upload endpoint.

In production this JPEG is a **real phone photo** the user takes of an actual shelf.

---

## 3. What CLIP is

**CLIP = Contrastive Language–Image Pre-training.** Open-sourced by OpenAI in 2021.

- Two encoders trained jointly on ~400 M `(image, caption)` pairs from the web.
- Both encoders emit a **fixed-length vector** in the same 512-dimensional space.
- Training objective: make each image vector close to *its* caption vector and far from every other caption in the batch (contrastive loss).
- Consequence: two photos of t-shirts land near each other in that 512-d space; a t-shirt image vector and a `"a photo of a mug"` text vector land far apart.

We use the **ViT-B/32** variant — Vision Transformer, "Base" size, 32-pixel image patches. It's the small/fast one: ~150 MB of weights, a few hundred ms per image on CPU. Bigger variants (`ViT-L/14`, `ViT-H/14`) exist and are stronger, but they need a GPU to be practical.

---

## 4. How we use CLIP locally (no API, no key)

CLIP weights are **fully open** — no auth, no per-call cost, no rate limits (other than the one-time HuggingFace download).

### 4.1 The stack

Declared as an **optional extra** in `pyproject.toml`:

```toml
ml = [
    "open-clip-torch>=2.29",
    "torch>=2.5",
    "torchvision>=0.20",
]
```

Installed with `pip install -e ".[ml]"`. That pulled:

- `torch 2.13.0+cpu` — CPU-only build, no CUDA / NVIDIA driver needed.
- `torchvision` — the image preprocessing pipeline (resize / crop / normalise).
- `open-clip-torch` — a well-maintained community re-implementation of OpenAI's CLIP with a broader model zoo.

### 4.2 First run: one-time weight download

The first time `CLIPProvider` is instantiated:

1. `open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")` calls out to HuggingFace **once** to download `open_clip_model.safetensors` (~150 MB) into
   `~/.cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/`.
2. That's the log line we saw during the live smoke:

   ```
   HEAD https://huggingface.co/timm/vit_base_patch32_clip_224.openai/... "HTTP/1.1 302 Found"
   Loading full pretrained weights from: C:\Users\...\snapshots\...\open_clip_model.safetensors
   ```
3. The `Warning: You are sending unauthenticated requests to the HF Hub` note is because we didn't set `HF_TOKEN` — fine, public models allow anonymous downloads with generous rate limits. Set `HF_TOKEN` if you get throttled.

Every subsequent run loads from disk cache. **Nothing hits the network.**

### 4.3 The `CLIPProvider` wrapper — `backend/model_router/clip_provider.py`

- Loads the model lazily (deferred import so `pytest` collection is fast).
- Auto-detects `cuda` if available, otherwise `cpu`. On this machine it's CPU.
- Exposes two methods:
  - `embed_image(paths: list[str]) -> list[list[float]]` — open files from disk, embed.
  - `embed_pil(images: list[PIL.Image]) -> list[list[float]]` — embed already-loaded PIL crops (this is what the matcher uses on Claude's bboxes).
- Inside `embed_pil`:
  1. Run each image through the torchvision preprocess transform: resize → 224×224 centre-crop → normalise with CLIP's `mean=(0.481, 0.458, 0.408)`, `std=(0.269, 0.261, 0.276)`.
  2. Stack into a batch tensor, move to device.
  3. `model.encode_image(batch)` inside `torch.no_grad()` — disables gradient tracking, halves memory and time.
  4. L2-normalise each vector.
  5. Return as plain Python `list[list[float]]` (so SQLAlchemy / pgvector can bind them without any tensor coupling).

L2-normalised 512-d vectors is exactly the shape pgvector's cosine distance is fastest on.

---

## 5. How CLIP plugs into the perception pipeline

```mermaid
flowchart LR
    A[User uploads display photo] --> B[POST /displays/analyze]
    B --> C[Persist JPEG + create Analysis pending]
    C --> D[Procrastinate defers avms.run_perception]
    D --> E[Worker calls Claude Sonnet 4.5<br/>vision_tool submit_scene_graph]
    E --> F[SceneGraph: N products,<br/>each with bbox x,y,w,h in 0..1]
    F --> G[For each bbox: PIL.crop the region]
    G --> H[CLIPProvider.embed_pil crops<br/>-> 512-d vectors]
    H --> I[pgvector NN search:<br/>Product.embedding.cosine_distance]
    I --> J[Attach product_id + confidence<br/>to each SceneGraph item]
    J --> K[Persist scene_graph JSONB<br/>on analyses row]
```

The nearest-neighbour lookup itself is a single SQL statement per bbox, using pgvector's HNSW cosine index we added in migration `c4e0d7f2a8b3`:

```python
select(Product, Product.embedding.cosine_distance(embedding).label("distance"))
    .where(Product.brand_id == brand_id, Product.embedding.is_not(None))
    .order_by("distance")
    .limit(1)
```

The HNSW index makes this sub-millisecond even at 100k+ SKUs — no `REINDEX` needed as the catalogue grows.

**One-line intuition:** *Claude finds what is on the shelf and where; CLIP tells us which specific SKU from the brand's catalogue that is.*

---

## 6. What runs where — network & cost cheatsheet

| Component | Runs where | Network calls | Cost |
|---|---|---|---|
| Pillow silhouette rendering | Local Python | — | Free |
| Mock display composition | Local Python | — | Free |
| CLIP weight download (first run) | HuggingFace CDN | ~150 MB, one-time | Free, no auth |
| CLIP embedding | Local CPU (torch) | — | Free (only your CPU time) |
| pgvector nearest-neighbour | Local Postgres (Docker) | — | Free |
| Perception (`SceneGraph`) | Anthropic API (Claude Sonnet 4.5) | Per-image call | ~$0.003-0.015 / image depending on resolution |
| Mockup generation (Phase 4) | Google Gemini image / Cloudflare fallback | Per-mockup call | TBD |

Everything except the Anthropic call is entirely local. If you unplug the internet after the first CLIP download, catalogue seeding + product matching + `GET /analyses/{id}` all still work — only `POST /displays/analyze` would fail, because it needs Claude to actually see the shelf.

---

## 7. Known follow-ups

- The live smoke matched **4 / 5** products correctly. The one miss was headphones → sneaker (`FTW-SNK-016` @ 0.831 instead of `TCH-HDP-029`). Root cause is that both silhouettes have a dominant rounded arc; CLIP's ViT-B/32 is small and can confuse coarse shapes on stylised drawings. Fixes to consider:
  - Higher-fidelity seed renders (or real product photos in production).
  - Per-category shortlist (only compare against products in the category Claude labelled the bbox).
  - Reweight cosine distance by colour histogram similarity for a cheap tiebreaker.
  - Upgrade to `ViT-L/14` if we have a GPU on the deployment box.
- The demo catalogue is procedural. Once Phase 2 (BrandProfile ingestion) lands, real product images replace these silhouettes and the confidence numbers should shoot up.
