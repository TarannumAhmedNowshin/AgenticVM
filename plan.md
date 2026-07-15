# Plan: Agentic Visual Merchandising Studio (AVMS)

## Concept

**AVMS** is a web app that turns a photo of any retail display into a scored, brand-aware improvement plan — with a visualised "after" mockup.

Flow: user uploads a display photo → **Perception** grounds the scene → **5-agent council** (Creative, Retail Psychology, Commercial + a Brand-Guardian critic + an Orchestrator) produces **9 tips (3 per specialist)** → a **rubric-driven scorer** returns before/after scores → an **image-edit model** renders a realistic "after" mockup. Every accept/reject feeds a per-brand learning loop.

---

## Chosen Stack

| Layer | Choice |
|---|---|
| Frontend | **Next.js** (App Router, TypeScript, Tailwind) — in `frontend/` |
| Backend / API / agents | **Python** (FastAPI + Claude Agent SDK) — in `backend/` |
| Reasoning + vision (perception + agents) | **Claude** via Anthropic SDK<br>• Main: `claude-sonnet-4-5-20250929`<br>• Orchestrator: `claude-opus-4-1-20250805`<br>• Small / fast: `claude-haiku-4-5-20251001` |
| Agent orchestration | **Claude Agent SDK** sub-agents + tool use |
| Text embeddings (brand RAG) | **Azure OpenAI `text-embedding-3-large`** (3072 dims) |
| Image embeddings (product matching) | **`open_clip_torch`** CLIP ViT-B/32 — local, CPU |
| After-mockup image editing | **Gemini 2.5 Flash Image** (free tier) |
| Fallback image gen | **Cloudflare Workers AI** (SDXL) — free tier |
| Database | **Postgres 16 + pgvector** — local Docker |
| Async jobs | **`procrastinate`** (Postgres-backed) |
| Image storage | Local filesystem (`backend/storage/`) |
| Auth | Basic email + password (FastAPI + bcrypt + JWT) |

---

## Five-Agent Council

| Agent | Model | Role |
|---|---|---|
| **Perception** | Sonnet 4.6 (vision) | Products, OCR, zones, palette, lighting → `SceneGraph` |
| **Creative** | Sonnet 4.6 | Composition, colour, framing, props |
| **Retail Psychology** | Sonnet 4.6 | Emotional cues, typography urgency, customer flow |
| **Commercial** | Sonnet 4.6 | Cross-sell, basket-building, top-seller placement |
| **Brand Guardian** *(Critic)* | Haiku 4.5 | Rejects off-brand / hallucinated tips |
| **Orchestrator** | Opus 4 | Dedupe, resolve conflicts, rank, guarantee 3×3=9, compute score, build mockup prompt |

---

## Phased Steps

### Phase 0 — Foundations
1. Repo layout: `frontend/` (Next.js) + `backend/` (Python: `api/`, `agents/`, `brand/`, `model_router/`, `db/`, `workers/`, `storage/`, `scripts/`, `tests/`).
2. `docker-compose.yml` for local Postgres 16 + pgvector.
3. Environment loading (`pydantic-settings`) from existing `.env`; add `.env.example`.
4. Basic auth: FastAPI + bcrypt + JWT; `users` table; `/auth/register`, `/auth/login`, `/auth/me`.
5. Postgres-backed async job runner (`procrastinate`).
6. `ModelRouter` abstraction with 4 providers: `ClaudeProvider`, `AzureEmbeddingProvider`, `CLIPProvider` (local), `GeminiImageProvider`.
7. `backend/scripts/seed_demo_brand.py` — synthetic brand + ~30 products so the pipeline is exercisable end-to-end from day one.

### Phase 1 — Perception pipeline
8. Send image to Claude Sonnet 4.6 vision → JSON: products, OCR text, zones, palette, lighting.
9. Post-process into a normalised `SceneGraph` (Pydantic model).
10. Product matcher: CLIP-embed each detected region + top-K similarity in pgvector against catalogue.
11. Enrich `SceneGraph` with matched SKUs, prices, category metadata.
12. *(Optional, later)* YOLOv8n on CPU if Claude's spatial precision isn't enough for UI overlay.

### Phase 2 — Brand knowledge base *(parallel with Phase 1)*
13. `BrandProfile` schema: identity (logo, palette, typography), voice (do/don't text pairs), aesthetic (reference images), audience persona, competitor set.
14. Multimodal ingestion: PDFs → chunk + Azure `text-embedding-3-large`; images → CLIP + captions; palettes → structured.
15. `BrandRAG` retriever: hybrid search (vector + keyword + colour distance).
16. `BrandUnderstandingScore` (0–100) shown live during upload.

### Phase 3 — Agent council *(depends on 1 & 2)*
17. Each specialist = Claude Agent SDK sub-agent with structured JSON `{tip, rationale, evidence[], impact_estimate, brand_refs[]}`. Sonnet 4.6.
18. Brand Guardian on Haiku 4.5 = validator + rule engine (colour clash, banned words, do/don't retrieval).
19. Orchestrator on Opus 4: dedupe, cluster conflicts, rank, guarantee 3 per specialist / 9 total, preserve provenance.

### Phase 4 — Scoring & after-mockup *(depends on 3)*
20. **Merchandising Rubric v1** — weighted axes (composition, colour harmony, focal clarity, hierarchy, cross-sell, brand alignment, signage). Versioned in `docs/rubric.md`.
21. Claude-based rubric scorer → per-axis + total, before/after.
22. After-Mockup Generator via Gemini 2.5 Flash Image; Cloudflare Workers AI SDXL fallback.
23. Before/after slider UI with per-tip toggles.

### Phase 5 — Web UX *(parallel with 3 & 4)*
24. Onboarding: brand upload wizard, live `BrandUnderstandingScore`.
25. Capture flow: camera + upload, EXIF strip, client-side thumbnail.
26. Analysis view: SceneGraph overlay, tabbed tips by agent, rationale + brand evidence, accept/reject/edit.
27. Result view: score dial, generated mockup, PDF brief export.
28. History & search per brand.

### Phase 6 — Feedback loop *(depends on 5)*
29. Log every accept/reject/edit with full context.
30. Nightly job re-ranks retrieval + updates per-brand prompt exemplars (few-shot memory, no retraining).
31. Per-brand agent-quality dashboard.

### Phase 7 — Trend intelligence *(independent after Phase 2)*
32. Ingestion from public trend sources (Pinterest APIs, retail blogs, seasonal reports).
33. Trend classifier: category, palette, motif, momentum (rising/plateau/dying).
34. Contextual trend hints in analysis view.

---

## Target File Structure

- `frontend/` — Next.js App Router
- `backend/`
  - `api/` — FastAPI routes, auth
  - `agents/perception/` — Claude-vision wrapper, SceneGraph builder
  - `agents/council/` — creative, psychology, commercial, guardian
  - `agents/orchestrator/` — Opus orchestrator
  - `agents/scoring/` — rubric + scorer
  - `agents/mockup/` — Gemini wrapper + Cloudflare fallback
  - `brand/` — BrandProfile, ingestion, RAG retriever
  - `model_router/` — provider abstraction (Claude / Azure / CLIP / Gemini)
  - `db/` — SQLAlchemy models + Alembic migrations
  - `workers/` — procrastinate workers
  - `storage/` — local uploads (gitignored)
  - `scripts/seed_demo_brand.py`
  - `tests/` — pytest
- `docker-compose.yml` — Postgres 16 + pgvector
- `plan.md`, `progress.md`, `docs/rubric.md`

---

## Verification

1. **Perception E2E** — 30 golden photos → ≥ 90% product-match precision vs seed catalogue.
2. **Brand-safety** — 10 seeded violations → Guardian rejects 100%.
3. **Determinism** — same input + brand_version + prompt_version → identical SceneGraph + stable ranking.
4. **Rubric audit** — reviewer vs system score ≥ 0.7 Spearman on 20 displays.
5. **E2E smoke** — upload → 9 tips → mockup → PDF export.
6. **Accessibility** — Lighthouse ≥ 90 on capture & analysis; camera works on iOS Safari + Android Chrome.

---

## Further Considerations

1. **Catalogue ingestion (post-POC)** — CSV first, then Shopify / Magento connectors, sitemap crawler fallback.
2. **Mockup fidelity** — Gemini layout-guided edit. Alternatives: annotated overlay (simpler) or full re-render (higher hallucination risk).
3. **Learning loop scope** — prompt-exemplar memory per brand. Later: periodic LoRA fine-tunes once data is sufficient.
4. **Local detector (YOLO)** — defer until Claude's spatial output proves insufficient.
