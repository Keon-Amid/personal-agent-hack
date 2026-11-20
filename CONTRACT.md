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
