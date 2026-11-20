# CONTRACT

Written together by the humans in hour 0. Only what is here is decided.

## Idea
TBD

## User + problem (one person, one number)
TBD

## Sponsors we use for real
TBD

## Lanes
- Keon:
- Brendan:
- Alistair:
- Kyle:

## Interfaces

### Products: `data/products.json` (owner: alistair) — DRAFT, confirm
`{"about", "products": [Product]}`, 48 real IKEA US products. Built by `python3 data/fetch_ikea.py $(cat data/sources.txt)`;
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
- `check_rug(product, room_width, room_depth, margin_in=6)` → [FitResult] (rug + 6 in from every wall; tries both orientations). `fit.options` uses it for rugs instead of the wall/floor checks
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

**Style labels per product (for cards):** each `ranked` entry has `product_styles`, e.g.
`[{"style": "scandinavian", "score": 0.0962}, {"style": "warm minimal", "score": 0.0944}]` (BORGEBY birch table).
Zero-shot by Superlinked SigLIP over the product photo, not hand-written; stored in `style_embeddings.json`
(`python3 data/sie.py labels` refreshes). Scores under ~0.05 are weak (most rugs and lamps): show them muted or not at all.

**Whole room:** call `R = sie.analyze_room(room_photo=bytes)` once (2 calls: embed + style labels), then
`sie.style_match(products, slot, emb, room=R)` per slot (1 rerank call each). Real run, 5 living-room slots from one
IKEA room photo: 4.7 s total, detected "dark modern".

### Senso knowledge base: `agent/senso_kb.py` (owner: alistair, A2) — loaded
All 48 products are in the team's Senso org as one document each (status `complete`; ids in `data/senso_index.json`).
Brendan's "Room Furnisher clearance rules" doc is the rules doc (not duplicated). Reload after catalog changes:
`python3 agent/senso_kb.py load` (skips unchanged docs). Loading cost ~0 credits; each fact-check ~0.01.

**Use `fit.claims.claim_text(product, fit_results)` to build the text you send to Senso.** It produces, per rule the
item was checked against: "Under our <rule> rule, <rule text>. Our catalog lists <name>, IKEA article <n>, as <fact>."
Live test (15:05): GLOSTAD sofa 10/10 and JÄRNVÄG rug 8/8 claims scored, all `grounded`; "Our catalog lists GLOSTAD as
84 inches wide" → `contradicts_kb`. `claims_for(...)` gives the same as `[{"rule", "text"}]` for the audit panel.

**Why that wording** (tested live, 14:50–15:05):
- Senso's `kb_accuracy` only scores claims it reads as about our org. Bare product facts ("GLOSTAD is 70 in wide")
  come back `about_brand: false`, **not scored** (`passed: null`, no KB search). "Our catalog lists …" and "Under our
  … rule" are scored.
- Always name the product with its **IKEA article number**. "KIVIK box 1 is 37.5 in wide" came back
  `contradicts_kb` (Senso matched the *black* KIVIK); with "IKEA article 394.405.93" it's `grounded`.
- Don't mix a fact and a rule in one sentence ("X is 70 in wide under the wall rule" → `unsupported_by_kb`).
- Room measurements aren't in Senso, so "wider than the 30 inch door" → `unsupported_by_kb`. The fit math is the
  authority for that; Senso verifies the spec and the rule it relies on.
- Read `claims[].passed` (true/false/null) and `claims[].bucket` (`grounded` / `contradicts_kb` / `unsupported_by_kb`
  / `general`) from `POST /org/evals/text {"text", "wait": true}`; evidence is in `evidence_chunks`.

### Pick one product per slot: `fit.pick.pick(options, style_match_result, budget_usd=None)` (owner: alistair) — DRAFT
Walks Superlinked's style ranking best-first; picks the first product that fits (and is within budget). Everything
ranked above it is rejected with the reason. Returns `{"slot", "picked": Option + style, "rejected": [...],
"audit": [AuditRecord]}` where the audit records follow brendan's shape (`step` rank/pick, `decision`
ranked/rejected/picked, `status`, `source`, `why`). Example `why` lines from a real run:
- `rejected` KIVIK: `style #1 of 7 (photo #1 0.062, text #3 0.995); no_fit: width 89.75 in > 88 in (user)`
- `picked` GLOSTAD: `style #3 of 7 (photo #2 0.057, text #4 0.966); fits; $199, 4.0★ (90 reviews), best value`

**Swap:** `pick(options, style, budget_usd, exclude=[product_ids already swapped away])` → the next style match that
fits; the excluded ones are logged as `swapped_out`. Reuse the same `style_match` result, so a swap makes no SIE call.

Senso's fact-check (brendan) runs on the picked item's claim after this.

### Agent: `agent/` (owner: brendan) — DRAFT, confirm
One backend, two front doors. The tools enforce the rules; the model only orders and explains them.
- **Web app (kyle wraps this):** `agent.agent.run_agent(room_input, photo_b64=None, style_text=None, budget_usd=None, on_event=None) -> Plan`.
  `room_input` = `{"wall", "depth", "door_width", "door_height"}` in inches (exact, source "user"). Runs `claude -p` (Claude Code
  on the host's Claude subscription, no API key) with only the MCP tools below; `on_event(audit_record)` streams progress.
  Real run: 5 slots in 135 s, 42/46 Senso claims verified, cart $1,027.97 → `contracts/plan.live.json`.
- **Tools** (`agent.tools`, also served by the MCP server): `create_plan`, `analyze_room`, `style_match`, `fit_options`, `pick`,
  `senso_check`, `swap`, `cart_add`, `get_plan`. `pick` only returns items that fit; `cart_add` refuses an item without a
  Senso check that has ≥1 verified claim and no conflict; every tool appends its own audit record and returns `plan_url`.
- **Anyone's own Claude:** `python -m agent.mcp_server` (stdio, for Claude Desktop / Claude Code) or `--http --port N`
  (claude.ai, needs public HTTPS). Setup in `docs/mcp.md`.
- **Plan** = `contracts/plan.live.json` shape: `plan_id, plan_url, room, style, items[] (slot, product, style rank/scores,
  fit {verdict, results}, senso {check_id, accuracy_pct, claims}, why, why_source, rejected[]), cart {items, total_usd,
  delivery_note, no_purchase: true}, audit[]`. Plans persist as JSON in `~/.cache/room-furnisher/plans/` (shared across processes).

### Scanned room + rearranging: `fit/scan.py`, `fit/layout.py` (owner: alistair) — DRAFT, confirm
`assets/room_scan_roomplan.glb` is a Polycam **Floorplan** (Apple RoomPlan) scan of the room we're in: every wall, the
door and each piece of furniture is its own named object (`Wall_0`, `Door_0`, `table_other_rect_0`,
`chair_dining_four_back_arms_1`, `television_0`, ...), in meters, Y up. Keon can `useGLTF` it and look objects up by name.

`fit.scan.load_scan(path)` → room model, inches, floor plane (x, z), item centres:
```json
{"walls": [{"id": "Wall_4", "a": [-96.9, 69.7], "b": [97.6, 69.7], "length_in": 194.5, "inner_length_in": 190.6}],
 "doors": [{"id": "Door_0", "center": [-96.9, -51.8], "width_in": 32.0, "height_in": 96.8, "axis": "z", "into_room": [1, 0]}],
 "items": [{"id": "table_other_rect_0", "label": "table_other_rect", "category": "table", "x_in": 21.9, "z_in": 6.2,
            "w_in": 90.7, "d_in": 44.5, "h_in": 29.8, "bottom_in": 0.4, "rotation": 0, "kind": "existing", "on_floor": true}],
 "outline": [[95.6, -53.7], [95.6, 67.7], [-95.0, 67.7], [-95.0, -72.0], [47.1, -72.0], [47.1, -53.7]]}
```
`a`/`b`/`length_in` are wall centrelines; `outline` and `inner_length_in` are the room-side faces (use these for fit).
Our room: L-shaped, interior 190.6 x 139.7 in, inner walls 190.6 / 142.1 / 139.7 / 121.4 in + a 48.5 x 18.3 in notch; door 32 x 97 in; a 91 x 45 in
table, 2 dining chairs, a swivel chair, a wall-mounted TV.

`fit.layout` (positions = item centre in inches, rotation 0/90/180/270):
- `layout_from_scan(room)` → the scanned furniture as a layout
- `add_product(layout, product, x_in, z_in, rotation)` → add an IKEA product (`kind: "new"`)
- `move(room, layout, item_id, x_in, z_in, rotation)` → `(new_layout, {item_id: [FitResult]})` — call on every drag
- `check_layout(room, layout)` → `{item_id: [FitResult]}`; checks `in_room`, `overlap`, `door_swing`, `clearance`
- `find_spot(room, layout, product)` → `{"x_in", "z_in", "rotation", "wall_gap_in", "results"}` or `None`:
  a spot where the product and every existing item still pass, closest to a wall
Rules: chairs may tuck under tables, anything may stand on a rug, rugs keep 6 in from walls, wall-mounted items
(bottom > 24 in) skip floor checks, `clearance` < 18 in → `unsure`. Real results: KIVIK at the door → "blocks the 32 in
door swing" + "corner outside the walls"; table pushed back → hits the L-shape notch; `find_spot(KIVIK)` → flush on
the 146 in wall.
