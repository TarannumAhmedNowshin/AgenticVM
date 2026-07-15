# AVMS — Progress Tracker

Living checklist of what's done, in-progress, and next. Update as work moves.

Legend: ✅ done · 🚧 in progress · ⏳ next · ⏸ deferred

---

## Phase 0 — Foundations

- ✅ Plan locked (see [plan.md](plan.md))
- ✅ Repo scaffold (code-complete)
  - ✅ `plan.md` + `progress.md`
  - ✅ `.gitignore` + `.env.example` (+ appended vars to real `.env`)
  - ✅ `docker-compose.yml` (Postgres 16 + pgvector)
  - ✅ `backend/pyproject.toml` + package layout
  - ✅ `backend/config.py` (pydantic-settings loading `.env`)
  - ✅ `backend/db/` (SQLAlchemy base, `User` model, Alembic init)
  - ✅ `backend/api/` (FastAPI app, JWT auth: `/auth/register`, `/auth/login`, `/auth/me`)
  - ✅ `backend/model_router/` (`ClaudeProvider`, `AzureEmbeddingProvider`, `CLIPProvider`, `GeminiImageProvider`)
  - ✅ `backend/agents/` skeletons (perception w/ `SceneGraph`, council w/ `Tip`, orchestrator, scoring, mockup)
  - ✅ `backend/brand/` package skeleton
  - ✅ `backend/workers/` (procrastinate app + placeholder `ping` task)
  - ✅ `backend/scripts/seed_demo_brand.py` stub
  - ✅ `backend/tests/` bootstrap (pytest + `/health` smoke test)
  - ✅ `frontend/` Next.js scaffold (App Router, TypeScript, Tailwind)
- ✅ Enable pgvector extension in Postgres (`CREATE EXTENSION vector` → v0.8.2)
- ✅ Generate + apply first Alembic migration (`users` table, `alembic_version` recorded)
- ✅ Smoke test: `docker compose up -d`, `alembic upgrade head`, `uvicorn backend.api.main:app` — `/health`, `/auth/register`, `/auth/login`, `/auth/me`, duplicate 409, missing-token 401 all verified. `pytest backend/tests` → 1 passed.
- ⏳ Seed demo brand end-to-end (real body lands in Phase 1)

## Phase 1 — Perception pipeline
- ✅ Claude vision wrapper (`ClaudeProvider.vision()` — free-form) + `vision_tool()` (schema-forced)
- ✅ Perception uses **Anthropic tool-use** for guaranteed structured JSON (no fragile regex)
- ✅ `SceneGraph` Pydantic model + tool-call `input_schema` + `prompt_version` / `model_id` stamps
- ✅ `perceive()` — Claude tool call → validated `SceneGraph` with prompt/model provenance
- ✅ Perception unit tests (success, empty scene, tool-call missing, schema violation) — all green
- ✅ `Brand` + `Product` SQLAlchemy models with `pgvector.Vector(512)` embedding column
- ✅ Alembic migration `8b3a1c5f9d21` — brands + products tables
- ✅ Alembic migration `c4e0d7f2a8b3` — swapped ivfflat → **hnsw** cosine index (no centroid training)
- ✅ Alembic migration `d92f3a1e6c47` — `displays` + `analyses` (JSONB scene graph, status enum)
- ✅ CLIP crop-matcher (`backend/brand/product_matcher.py`) — bbox crop → embed → nearest-neighbour via `Product.embedding.cosine_distance`, enriches `SceneGraph` in place
- ✅ `CLIPProvider.embed_pil()` for in-memory PIL crops
- ✅ **`POST /displays/analyze`** — upload photo, persist under `storage/displays/<slug>/`, enqueue perception, returns 202 + IDs
- ✅ **`GET /analyses/{id}`** — poll status + scene graph, scoped to owning user
- ✅ **`avms.run_perception` procrastinate task** — pending → running → complete/failed transitions, mocked-perception worker tests
- ✅ `seed_demo_brand.py` — inserts demo brand + 30 SKUs with **category-specific silhouettes** (t-shirt / bottle / shoe / bag / mug / headphones / …) instead of solid tiles, so CLIP embeddings actually separate
- ✅ Real Anthropic model IDs pinned everywhere (`claude-sonnet-4-5-20250929`, `claude-opus-4-1-20250805`, `claude-haiku-4-5-20251001`)
- ✅ `pip install -e ".[ml]"` — torch 2.13.0+cpu + open-clip installed
- ✅ Re-seed populates real 512-dim CLIP vectors (30/30 products)
- ✅ **Live E2E verified end-to-end** — real photo → HTTP upload → procrastinate worker → live Claude Sonnet 4.5 vision → CLIP crop-match → persisted scene graph (see "Latest change" below)

## Phase 2 — Brand knowledge base
- ⏳ `BrandProfile` schema
- ⏳ Multimodal ingestion (PDF + images + palette)
- ⏳ `BrandRAG` hybrid retriever
- ⏳ `BrandUnderstandingScore`

## Phase 3 — Agent council
- ⏳ Creative / Psychology / Commercial specialist sub-agents
- ⏳ Brand Guardian critic
- ⏳ Orchestrator (Opus)

## Phase 4 — Scoring & after-mockup
- ⏳ Rubric v1 (`docs/rubric.md`)
- ⏳ Rubric-driven scorer
- ⏳ Gemini image editor + Cloudflare fallback

## Phase 5 — Web UX
- ⏳ Brand upload wizard
- ⏳ Capture flow (camera + upload)
- ⏳ Analysis view (SceneGraph overlay + tabbed tips)
- ⏳ Result view (score dial + mockup + PDF export)
- ⏳ History & search

## Phase 6 — Feedback loop
- ⏳ Accept/reject logging
- ⏳ Nightly re-rank + prompt exemplar updates
- ⏳ Agent-quality dashboard

## Phase 7 — Trend intelligence
- ⏸ Deferred until POC validated

---

## Latest change
**Phase 1 live end-to-end verification (HTTP + worker + real Claude + real CLIP).**

Landed on top of the previous hardening pass:
- **`[ml]` extra installed** — `torch 2.13.0+cpu`, `open-clip-torch`, and
  transitive deps. CLIP now loads `ViT-B-32` / `openai` pretrained on CPU.
- **Real CLIP embeddings** — re-ran `seed_demo_brand.py`; every demo product
  now carries a 512-d embedding computed from its silhouette PNG.
- **Procrastinate schema applied** to the same Postgres instance
  (`procrastinate_jobs`, events, workers).
- **Mock display JPEG** — `backend/scripts/build_mock_display.py` renders
  a 1280×960 shelf composite (t-shirt, mug, perfume, sneaker, headphones +
  navy signage banner + red "TODAY $45" price tag) at
  `backend/storage/smoke/mock_display.jpg`.
- **In-process smoke** — `backend/scripts/live_smoke.py` drives
  `_run_perception` directly. Claude Sonnet 4.5 returned 5 products +
  banner text + palette; scene graph persisted to
  `backend/storage/smoke/scene_9.json`.
- **Windows event-loop fix** — psycopg async requires `SelectorEventLoop`
  but Windows defaults to `ProactorEventLoop`. Fixed in three places:
  1. `backend/workers/app.py` sets `WindowsSelectorEventLoopPolicy` at
     import time (worker CLI path).
  2. `backend/api/main.py` adds a FastAPI `lifespan` that opens the shared
     procrastinate `App` so route handlers can `defer_async` without
     hitting `AppNotOpen`.
  3. `backend/scripts/run_api.py` — new runner that drives uvicorn via
     `asyncio.Runner(loop_factory=SelectorEventLoop)` (Python 3.14
     ignores the now-deprecated `set_event_loop_policy`).
- **HTTP + worker smoke** — `backend/scripts/http_smoke.py` registers a
  user, uploads the mock display via `POST /displays/analyze`, and polls
  `GET /analyses/{id}` until terminal. End-to-end result (job id 2):
  `analysis 11 status=COMPLETE model=claude-sonnet-4-5-20250929 prompt_version=c3264446f288 products=5`,
  procrastinate job `succeeded` in 23.7 s.

Known follow-ups (not blockers for Phase 2):
- One CLIP mismatch on the smoke image: headphones matched `FTW-SNK-016`
  instead of `TCH-HDP-029` (silhouette confusion). Fix belongs in matcher
  tuning — either richer seed renders or a per-category vocabulary prior.
- JWT secret is 20 bytes; `InsecureKeyLengthWarning` prints on each token
  op. Bump to ≥32 bytes before shipping.

Test suite unchanged: **12 passed, 0 failed.**

### Next
- Kick off Phase 2: `BrandProfile` schema + multimodal ingestion
  (PDF via Azure text-embedding-3-large 3072-d, brand images via CLIP +
  captions, colour palette structured), `BrandRAG` hybrid retriever
  (vector + keyword + colour distance), `BrandUnderstandingScore` (0-100).
