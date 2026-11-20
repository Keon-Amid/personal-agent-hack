# Review of brendan's Room Furnisher spec (from alistair's lane: data + fit)

Checked against `CONTEXT.md` on main and what's already built in `data/` and `fit/` (main, 522f6a8).
Facts only; which way to go is a human decision for `CONTRACT.md`.

## Conflicts with CONTEXT.md

| # | Spec says | CONTEXT.md / main says | Why it matters |
|---|---|---|---|
| 1 | One Next.js TypeScript repo; fit code in `/lib/fit` (TS) | React + Vite + R3F front end, **Python + FastAPI** back end. `fit/` already exists in Python with 10 tests | Pick one before anyone writes more code. If we go TS, `fit/` needs porting (small, ~100 lines) |
| 2 | Sponsors: Senso + **Statsig + SingleStore** | Senso + **Superlinked** core, Amplitude easy add; **SingleStore listed as skip** | Superlinked (2 prizes, founder is a judge) disappears from the spec |
| 3 | 2D SVG floor plan; 3D is a stretch | "3D room" is in the one-line plan; R3F with scaled low-poly models | Changes Keon's whole lane |
| 4 | Lanes A–D unnamed; fit module owned by B (agent) | Alistair = data **+ fit math**; Brendan = agent; Kyle = backend; Keon = UI | Who owns fit? |
| 5 | Mock checkout | "Real cart, held for approval. No fake store" | Changes the "meaningful action" claim |

## Out of date inside the spec

- **Finding #2 (no Senso REST verify endpoint) is superseded by brendan's own channel post:** `POST /api/v1/org/evals/text` with `wait: true` works (~7 s, no credits, needs a User-Agent header). So the fact-check can run from code, not just MCP.
- Finding #9 says the Node driver is `singlestore-nodejs`, but the stack table still says `mysql2`.

## Catalog (Role A in the spec): what already exists vs. what the spec asks for

**Already on main:** `data/products.json`, **44 real IKEA US products in 14 categories**, fetched by `data/fetch_ikea.py`
from `data/sources.txt` (rebuildable in ~30 s). Every number is read from the product page and cross-checked;
nothing is typed by hand. That's stronger than the spec's "collected by hand in a shared sheet" for the
"never type a number" rule.

Gaps vs. the spec's `Product` type:

| Spec field | Status |
|---|---|
| `width_in/depth_in/height_in` | Have, as `dims_in.{w,d,h}` (plus `packages_in` for box sizes) |
| `price_usd`, `url`, `store` | Have (`source_url`, `retailer`); 1 product has no price |
| `image_url` | **Missing**, but on every IKEA page; easy to add |
| `style_tags` (Warm Minimal / Mid-Century / Cozy Eclectic) | **Missing**; needs either Superlinked/Claude tagging or hand tags (label them) |
| `delivery_days` | **Missing**; IKEA pages don't show a per-product delivery time without a ZIP. Don't invent it |
| Categories `sofa, rug, coffee_table, chair, lamp, shelf` | Ours: `armchair`, `floor_lamp`, `bookcase` etc. A rename map is trivial |
| One store only | Everything is IKEA so far |

**Oversized-rug seeding is unnecessary:** real data already gives a negative control. Against an 88 in wall,
KIVIK (89.75 in) and UPPLAND (88.25 in) are too wide, from IKEA's own numbers.

## Fit checks: spec vs. `fit/` on main

| Check | Spec | `fit/` |
|---|---|---|
| Item width on a wall | ✓ | ✓ `check_wall` |
| 36 in walkway | ✓ | ✓ `check_floor` |
| **Boxes through the doorway** | not in spec | ✓ `check_doorway` (every package) — a differentiator: "the sofa box won't fit through your door" |
| Door-swing arc clear | ✓ | ✗ needs x/y placement; can add once `Placement` is agreed |
| Rug ≥ 6 in from walls | ✓ | ✗ easy to add |
| Measurement error (photo estimate ± in) | not in spec (tape measure only) | ✓ verdict `unsure` when the answer depends on the error |

Verdicts: spec has `verified | conflict`; `fit/` has `fits | unsure | no_fit`. `fits→verified`, `no_fit→conflict`;
`unsure` only matters if room sizes can be estimated from the photo (CONTEXT.md says they are). If we
tape-measure only, `unsure` never happens and the two match.
