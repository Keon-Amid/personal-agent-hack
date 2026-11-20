# Sprint roadmap (PROPOSED, brendan)

Not decided until the team agrees; see `CONTRACT.md`. Written 13:15. Submission is 16:30.

## What was validated at 13:15 (real calls, not assumptions)

| Assumption | Result |
|---|---|
| `fit.options(products, category, room)` gives fit + best value per category | ✓ on main, tests pass |
| `sie.rank(...)` gives a Superlinked style rank + score | ✓ on main (alistair, 292bbca) |
| Catalog covers the living-room slots | ✓ sofa 7, armchair 4, coffee_table 4, rug 3, floor_lamp 3 |
| Real negative control exists | ✓ HYLTARP 91.4 in, KIVIK 89.8 in, UPPLAND 88.3 in vs an 88 in wall |
| Senso returns `conflict` with the rule quoted | ✓ claim "24 in walkway" → **conflict**, quote "keep at least 36 inches of clear walkway" |
| Senso returns `verified` with the rule quoted | ✓ "36 in walkway" and "every box fits through the doorway" → **verified**, 100% |
| IKEA delivery dates by ZIP | ✗ IKEA US shows none (alistair). Cart shows "home delivery from $29" + IKEA link |

**Design consequence:** Senso checks *facts in its knowledge base* (rules, product specs, prices). It does not do
the room arithmetic. So the split is:
- `fit/` decides whether an item fits this room (the math, with measurement error).
- Senso verifies every fact the agent states in its reason (spec, rule, price) before the item goes in the cart.
  A `conflict` means the agent misstated something, so it rewrites or rejects. A `no_fit` means the item really
  doesn't fit, so it swaps.
- Spike S1 below tests whether Senso can also catch room conflicts when the room's measurements are added to the
  KB as a document. If yes, that becomes the demo moment; if not, the demo moment is `no_fit` + Senso-verified rule.

## Timeline

| Sprint | Time | Goal | Exit check |
|---|---|---|---|
| **0: Unblock** | 13:15–13:35 | Contract merged, fixture on main, keys, skeletons | Every lane can code against `contracts/plan.example.json` |
| **1: Build in parallel** | 13:35–14:30 | Each part works alone on real data | **14:30: first full run** photo/measurements → plan → 3D → cart |
| **2: Integrate + demo moment** | 14:30–15:30 | One path end to end, the swap moment reliable | **15:30: demo works** twice in a row |
| **3: Freeze + ship** | 15:30–16:15 | Video, README, repo public, submit | 16:00 freeze, 16:15 submitted |

## Shared shapes (frozen at 13:35)

`contracts/plan.example.json` is the single fixture every lane builds against. Room uses alistair's `fit.room()`.

```json
{"plan_id": "demo-1",
 "room": {"wall": {"value_in": 88, "error_in": 4, "source": "estimated:door"},
          "depth": {"value_in": 150, "error_in": 6, "source": "estimated:door"},
          "door_width": {"value_in": 30, "error_in": 0, "source": "user"},
          "door_height": {"value_in": 80, "error_in": 0, "source": "user"},
          "photo_url": "..."},
 "items": [{"slot": "sofa", "product_id": "ikea-...", "name": "...", "price_usd": 449.0,
            "dims_in": {"w": 79.1, "d": 35.0, "h": 31.5}, "image_url": "...", "source_url": "...",
            "style": {"rank": 1, "score": 0.86},
            "fit": {"verdict": "fits", "results": ["FitResult"]},
            "senso": {"check_id": "...", "claims": [{"claim": "...", "verdict": "verified", "quote": "..."}]},
            "why": "one line", "rejected": [{"product_id": "ikea-kivik-...", "why": "no_fit: width 89.75 in > 88 in"}]}],
 "cart": {"total_usd": 1234.0, "delivery_note": "IKEA home delivery from $29", "no_purchase": true},
 "audit": ["AuditRecord, see CONTRACT.md"]}
```
Slots: `sofa`, `armchair`, `coffee_table`, `rug`, `floor_lamp`. Layout is a fixed template per slot (no LLM coordinates).

## Update 13:30
alistair shipped `sie.style_match()` and `fit.pick.pick()` (d77ec25): real run rejects style #1 KIVIK (89.75 in > 88 in wall) and picks GLOSTAD, with audit records in our shape. A5 shrinks to glue + Claude reason + Senso check.

## Work packages

Each package owns its files, so packages can run as parallel agents without touching the same file.
"Depends" means it needs the other package's *interface*, which the fixture already provides.

### Brendan's lane (agent): 6 packages, all parallel after A1

| Id | Package | Files it owns | Done when | Depends |
|---|---|---|---|---|
| **A1** | Fixture + types | `contracts/plan.example.json`, `agent/types.py` | Fixture valid JSON, uses real catalog ids, includes 1 rejected item | — (do first, ~15 min) |
| **A2** | Senso KB loader (offer to alistair: data-adjacent, his lane is free) | `agent/senso_kb.py`, `data/senso_index.json` | Rules doc + 1 doc per catalog product (name, dims, boxes, price, URL) loaded idempotently; `senso search context "KIVIK width"` returns the spec | — |
| **A3** | Senso check client | `agent/senso.py`, `agent/test_senso.py` | `check(text, question) → {check_id, accuracy_pct, claims:[{claim, verdict, quote}]}`; sets a User-Agent; caches by text hash; test against the live rules doc | — |
| **A4** | Room estimator | `agent/room.py`, `agent/test_room.py` | Claude vision on a photo → `fit.room()` with `error_in` and `source: "estimated:door"`; exact values override; works with no photo | needs `ANTHROPIC_API_KEY` |
| **A5** | Orchestrator (slimmed: alistair's `fit.pick` + `sie.style_match` already do rank → fit → pick → rejected → audit) | `agent/plan.py`, `agent/test_plan.py` | `plan(room, photo) → Plan` matching the fixture: per slot call `sie.style_match` + `fit.options` + `fit.pick`; Claude writes the one-line reason from the picked item's facts; `senso.check` on that reason; on `conflict`, rewrite once then reject; merge audit records; `swap(plan, slot)` = next item from pick's ranking | A1 shape; mocks A3/A4 until they land |
| **S1** | Spike: room facts in Senso | `agent/spike_room_senso.py` (throwaway) | Answer in one line: does adding "living room north wall is 88 in" to the KB make "KIVIK (89.75 in) fits the north wall" come back `conflict`? | A2 rules loaded ✓ |

### Other lanes (owners confirm)

| Id | Owner | Package | Done when |
|---|---|---|---|
| U1 | keon | 3D room from `plan.example.json` (R3F boxes at real W×D×H) | Renders the fixture |
| U2 | keon | Item panel + audit timeline | Shows fit math, style rank, Senso verdict + quote, rejected items |
| U3 | keon | Measurement input + cart panel + Amplitude events | `unsure` prompts one measurement; cart lists IKEA links, total, "no purchase" |
| D1 | alistair | ✓ done (d77ec25): `sie.style_match` + `fit.pick`. Next: rug-from-walls check | `check_rug` in `fit/` |
| D2 | alistair | Catalog QA: every slot has ≥1 fitting + ≥1 non-fitting item for the demo room | Listed in a comment in `data/` |
| K1 | kyle | FastAPI app wrapping `agent.plan` / `swap` / `room` per CONTRACT endpoints; serves the fixture until A5 lands | `curl /api/plan` returns the fixture, then real data |
| K2 | kyle | Demo video + submission checklist | Video link by 16:00 |

## Gates (call them out loud)

- **14:30 G1:** first full run. If A5 isn't real yet, the UI runs on the fixture and A5 keeps going. Cut A4 (photo
  estimate) first; typed measurements are enough.
- **15:30 G2:** demo twice in a row. If Senso is flaky, use cached checks from a real earlier run (labelled).
- **16:00:** freeze, repo public. **16:15:** submitted.

## Cut order (first to go)

1. A4 photo estimate (type measurements) 2. S1 room-facts conflict 3. Amplitude 4. swap UI (keep rejected list)
