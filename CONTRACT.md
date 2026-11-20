# CONTRACT

Written together by the humans in hour 0. Only what is here is decided.

> **DRAFT from brendan (branch `brendan/contract-draft`).** Sections marked PROPOSED are not decided until the four
> of us agree and this merges to main. Alistair's interface sections below are unchanged.

## Idea — PROPOSED
A room-furnishing shopping agent. The person uploads a photo of a room. The agent estimates the room's size, picks
real IKEA products that match the room's style (Superlinked), **proves each one fits** (our `fit/` checks: wall, floor,
walkway, every box through the doorway) and **has Senso fact-check each claim** before it goes in the cart. The result
is a 3D room (React Three Fiber, products as boxes scaled to real W×D×H), an audit trail on every item, and a real
cart of IKEA links. Not a chat app.

**Demo moment:** a real IKEA product fails on real numbers (e.g. KIVIK sofa 89.75 in on an 88 in wall, or its box
won't clear the door), Senso returns `conflict` with the rule quoted, and the agent swaps in the next best option that
fits. No staged data.

**Decided by brendan, to confirm with the team:**
1. **Cart:** nothing is bought. The cart is real IKEA products, each linking to its IKEA page, with totals. UI and
   pitch say "no purchase is made".
2. **Style:** Superlinked ranks products against the room's style (embeddings + reranker), scores shown in the audit
   trail. No hand-written style tags.
3. **Measurements:** estimated from the photo by default (each carries `error_in`). The person can enter exact
   measurements at any time; an `unsure` verdict asks for that one measurement.
4. **Delivery:** use brendan's real ZIP for delivery estimates if IKEA returns them to a script (unverified). The ZIP
   lives in `.env` as `DEMO_ZIP`, never in the repo. If it doesn't work, show no delivery date rather than invent one.

**Out:** real payment, 3 side-by-side designs, style quiz, Gemini renders, SingleStore, Statsig config versions.

## User + problem (one person, one number)
TBD — still open. Options from CONTEXT.md: college student furnishing a dorm, renter with lease limits, or a
resettlement caseworker. Needs one real number (e.g. return cost of furniture that doesn't fit).

## Sponsors we use for real — PROPOSED
| Sponsor | Exact use |
|---|---|
| **Senso** (core) | KB holds the room rules (walkway, door clearance, rug margins) and product specs. Every "fits and is allowed" claim goes to `POST /api/v1/org/evals/text`; the verdict, check id and quoted passage go in the audit record. |
| **Superlinked SIE** (core) | Embed the room photo/style and each product's image + text; rerank candidates per category; scores shown in the audit trail. Needs `SIE_API_KEY` by 13:30, else fall back to Claude ranking and drop the track. |
| Amplitude (easy add) | UI events: item swapped, measurement entered, cart opened. |

## Lanes — PROPOSED
- **Keon (UI):** 3D room (R3F), item cards, audit-trail timeline, measurement input, cart panel, Amplitude events.
- **Brendan (agent):** photo → room estimate → slots → pick (using `fit.options` + Superlinked scores) → Senso check →
  audit records. Senso KB loading.
- **Alistair (data + fit):** catalog, `fit/` checks and options, Superlinked embeddings/rerank, delivery-by-ZIP check.
- **Kyle (backend + glue):** FastAPI app and endpoints below, cart, deploy, demo video, submission.

## Interfaces

### Products: `data/products.json` (owner: alistair) — DRAFT, confirm
`{"about", "products": [Product]}`, 44 real IKEA US products. Built by `python3 data/fetch_ikea.py $(cat data/sources.txt)`;
every number is read from `source_url`, nothing typed by hand.
Categories: sofa, armchair, coffee_table, side_table, desk, dining_table, dining_chair, dresser, nightstand,
tv_bench, rug, floor_lamp, bookcase, bed.
```json
{"id": "ikea-kivik-sofa-tibbleby-beige-gray-39440593", "retailer": "IKEA", "name": "KIVIK Sofa - Tibbleby beige/gray",
 "article_number": "394.405.93", "category": "sofa", "price_usd": 799.0, "price_note": null,
 "dims_in": {"w": 89.75, "d": 37.375, "h": 32.625},
 "dims_raw": {"width": 89.75, "seat height": 17.75, "...": "every measurement the page lists"},
 "packages_in": [{"w": 37.5, "d": 72.5, "h": 19.75}],
 "image_url": "https://www.ikea.com/us/en/images/products/...__..._s5.jpg",
 "image_urls": ["main photo first, then every other photo on the page (4-13 per product)"],
 "source_url": "https://www.ikea.com/us/en/p/...", "fetched_at": "2026-11-20T20:49:27+00:00"}
```
Round items (tables, lamps) use the diameter for w and d. `price_usd` can be null (1 product) and may be a
temporary IKEA Family price. `h` can be null for a rug.

### Fit checks: `fit/` Python module (owner: alistair) — DRAFT, confirm
All inches. A room measurement carries where it came from and how far off it may be:
`measurement(value_in, error_in=0, source="user" | "estimated:door" | "estimated:paper")`
- `check_wall(product, wall, clearance_in=0)` → FitResult
- `check_floor(product, room_depth, walkway_in=36)` → FitResult (item against a wall + walkway in front)
- `check_doorway(product, door_width, door_height)` → [FitResult] (every package, or the assembled item)
- `overall([FitResult])` → worst verdict

FitResult (goes straight into the audit record):
```json
{"check": "wall", "verdict": "fits|unsure|no_fit",
 "math": "width 89.75 in > 88 in (user)", "need_in": 89.75,
 "available": {"value_in": 88, "error_in": 0, "source": "user"}, "margin_in": -1.75}
```
`unsure` = the answer depends on the measurement error → the UI asks the person to measure that one thing.

### Price vs. quality options: `fit.options` (owner: alistair) — DRAFT, confirm
`room(wall, depth, door_width, door_height)` (each a `measurement`), then `options(products, category, room)` →
list sorted by price:
```json
{"id": "...", "name": "...", "price_usd": 449.0, "rating": 4.6, "review_count": 20,
 "image_url": "...", "source_url": "...", "fit": "fits|unsure|no_fit", "fit_results": [FitResult],
 "best_value": true, "why": "best value: nothing that fits is cheaper and better rated"}
```
Quality = IKEA's customer rating (`rating`, 1–5, with `review_count`). `best_value` = fits, 10+ reviews, and no other
fitting product with 10+ reviews is both cheaper and better rated (the price/quality frontier). `why` is one line
for the audit trail. Chart: price on x, rating on y, dot size = reviews, shape/colour = fit, line through best values.

### Style match: `data/sie.py` (owner: alistair, Superlinked SIE) — DRAFT, confirm
Every product's main IKEA photo is embedded once with `google/siglip-so400m-patch14-384` on Superlinked SIE into
`data/style_embeddings.json` (`{"model", "input", "created_at", "vectors": {product_id: [1152 floats]}}`;
rebuild with `python3 data/sie.py build`, needs `SIE_API_KEY`). At run time:
- `sie.query_photo(room_photo_bytes)` or `sie.query_text("warm minimal light wood")` → query vector (1 API call)
- `sie.rank(products, category, query_vec, emb)` → products in that category, best match first:
```json
{"id": "...", "name": "...", "style_score": 0.8627, "style_source": {"kind": "superlinked", "model": "google/siglip-so400m-patch14-384"}}
```
`style_score` is cosine similarity. **Compare scores only within one query:** photo→photo scores sit around 0.5–0.9,
text→photo around 0–0.1. Show rank (and the score) in the audit trail, not an absolute threshold.

**Full style step (use this):** `sie.style_match(products, category, emb, room_photo=bytes | style_text=str)`
1. Room photo → SigLIP → `detected_style` (zero-shot over `sie.STYLES`, e.g. "dark modern 0.124").
2. Photo match: product photos vs the room photo.
3. Text match: Superlinked reranker `Qwen/Qwen3-Reranker-4B` over IKEA's name/colour/material/description vs the style.
4. Reciprocal rank fusion (k=60) of the two rankings.
```json
{"category": "sofa", "style_text": "...", "detected_style": [{"style": "dark modern", "score": 0.1244}] | null,
 "source": {"kind": "superlinked", "embed_model": "google/siglip-so400m-patch14-384",
            "rerank_model": "Qwen/Qwen3-Reranker-4B", "fusion": "reciprocal rank fusion, k=60"},
 "ranked": [{"id": "...", "style_rank": 1, "style_fused": 0.0328, "photo_rank": 1, "photo_score": 0.062,
             "text_rank": 3, "text_score": 0.995}]}
```
Cost: 2–3 SIE calls per category (~3 credits for the rerank). ~2–5 s.

### Pick one product per slot: `fit.pick.pick(options, style_match_result, budget_usd=None)` (owner: alistair) — DRAFT
Walks Superlinked's style ranking best-first; picks the first product that fits (and is within budget). Everything
ranked above it is rejected with the reason. Returns `{"slot", "picked": Option + style, "rejected": [...],
"audit": [AuditRecord]}` where the audit records follow brendan's shape (`step` rank/pick, `decision`
ranked/rejected/picked, `status`, `source`, `why`). Example `why` lines from a real run:
- `rejected` KIVIK: `style #1 of 7 (photo #1 0.062, text #3 0.995); no_fit: width 89.75 in > 88 in (user)`
- `picked` GLOSTAD: `style #3 of 7 (photo #2 0.057, text #4 0.966); fits; $199, 4.0★ (90 reviews), best value`

Senso's fact-check (brendan) runs on the picked item's claim after this.

### Audit record (owner: brendan) — PROPOSED
Every step appends one record; the UI renders them as a timeline and per-item panel.
```json
{"ts": "2026-11-20T14:02:11Z", "step": "estimate_room|rank|fit_check|senso_check|pick|swap|cart",
 "item_slot": "sofa", "product_id": "ikea-...", "input": "short text",
 "source": {"kind": "photo|catalog|fit|superlinked|senso", "url": "...", "passage": "...",
            "senso_check_id": "...", "content_id": "...", "score": 0.82},
 "decision": "picked|rejected|asked_user", "why": "one line",
 "status": "verified|conflict|unsupported|fits|unsure|no_fit"}
```

### Endpoints: FastAPI (owner: kyle) — PROPOSED
| Endpoint | Input | Returns |
|---|---|---|
| `POST /api/room` | photo + optional exact measurements | `Room` (walls, door; each a `measurement` with source and error) |
| `POST /api/room/measure` | room id + one exact measurement | updated `Room`; re-runs fit on the plan |
| `POST /api/plan` | room id | items per slot: product, fit results, Superlinked score, Senso verdict, audit records |
| `POST /api/swap` | plan id + slot | next item, with the rejected candidates and why |
| `GET /api/cart` | plan id | IKEA links, prices, total, delivery if known, full audit trail |
