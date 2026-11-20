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
`{"about", "fetched_at", "products": [Product]}`. Every number is read from `source_url`; nothing typed by hand.
```json
{"id": "ikea-kivik-sofa", "retailer": "IKEA", "name": "...", "article_number": "394.405.93",
 "category": "sofa|armchair|bookcase|bed|...", "price_usd": 799.0, "price_note": "string or null",
 "dims_in": {"w": 89.75, "d": 37.375, "h": 32.625},
 "packages_in": [{"w": 37.5, "d": 72.5, "h": 19.75}],
 "source_url": "https://www.ikea.com/us/en/p/..."}
```

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
