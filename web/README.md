# web/ — the app

A shopping agent that furnishes a scanned room with real IKEA pieces and shows the measurement behind every choice.

```bash
cd web && npm install && npm run dev      # http://localhost:5173
```

## What you can do

1. **Start**: drop a `.glb` room scan (Polycam on an iPhone Pro), or open one of today's rooms.
2. **Describe the room you want** in the bar at the bottom and press Enter. The agent's steps stream into the
   **audit trail** on the left while each piece lands in the 3D room.
3. **Click a piece** (in the room or the trail): fit checks with their maths, Senso's claims with the quoted source,
   what was rejected first, and the alternatives as a price-against-rating chart. Swap to any that fits.
4. **Measure**: click Wall, Depth or Door width in the top bar and type a tape measurement. Every piece is re-checked,
   the change is logged, and anything that no longer fits turns red with a one-click swap.
5. **Cart**: approve it (recorded in the audit trail), open every piece on IKEA, download the trail as JSON.
   No order is placed; you pay on IKEA.com.

Keys: `⌘K` describe, `←` `→` step through pieces, `1` `2` `3` views, `esc` close.

## Where the data comes from

| On screen | Source |
|---|---|
| Plans, audit records, Senso claims | `contracts/plan.*.json`: recorded runs of `agent.agent.run_agent` |
| Products, prices, sizes, ratings, photos | `data/products.json` |
| Alternatives and their fit checks | `src/fixtures/options.*.json`, written by `python3 web/scripts/make_options.py` from `fit.options` |
| The room | `assets/room_scan_roomplan.glb` (Polycam Floorplan scan), or drawn from a plan's typed measurements |
| Product 3D models | `public/models/` (see below); anything without one is a plain shape at the listed size |

**Live or replay, decided by itself.** Run everything with one command from the repo root:

```bash
./scripts/dev.sh        # agent server on :8000 + this app on :5173
```

The app asks the agent server (`server/app.py`, proxied at `/api`) how it is doing every few seconds:

- **Server up, with `SENSO_API_KEY` and `SIE_API_KEY` in `.env`** → the pill says "Live agent ready". Describing a room
  starts a real run (`POST /api/plan` with the room's measurements, your words and your budget as `budget_total_usd`),
  and the app follows `GET /api/plan/{id}` once a second. Approving the cart calls `POST /api/plan/{id}/approve`.
- **Anything else** → the pill says "Replay of a real run" and the app plays back a recorded run from `contracts/`:
  same records, same order, same text, with the waiting shortened. Hover the pill to see what is missing.

`/plan/<id>` works for any plan the server knows, including ones started from Claude Desktop through the MCP server:
the page shows what exists so far and keeps following while the agent works. `API_TARGET=http://<host>:8000 npm run dev`
points the app at a teammate's server. `VITE_API=mock` or `VITE_API=live` forces one mode.

Computed in the browser, and labelled as yours in the trail: a tape measurement re-checks each piece from the
`need_in` its fit result already carries (same comparison as `fit/checks.py`), and a swap takes its fit checks from
`fit.options`. A swapped piece shows "Not checked by Senso yet" until the agent runs again.

Deep links: `/plan/<plan_id>` opens a finished plan. `?at=ready|run|done`, `?sel=<slot>`, `?cam=iso|top|front`,
`?cart=1` set the first view (handy for rehearsing).

## Layout

- `src/ui/`: the panels (start screen, top bar, audit trail, item panel, cart, command bar)
- `src/scene/`: the 3D room the app draws (scan parsing, layout, furniture, camera)
- `src/store.ts`: one store; `applyRecord` is the only place a run changes what is shown
- `src/api/`: `mock.ts` (replay) and `live.ts` (agent server), same interface
- `src/styles/tokens.css`: colours, type, radii
- `src/room3d/` + `src/Harness.tsx`: kyle's standalone renderer and its test page, at **`/harness`**

---

# The standalone 3D renderer (`src/room3d/`)

`src/room3d/` draws the room: a box built from the room's measurements, each picked product at its real
IKEA width × depth × height, and the fit verdict as the outline colour (green fits, amber unsure, red does not fit).

```tsx
import { RoomScene, fromAgentPlan } from './room3d'
import './room3d/room3d.css'

const plan = fromAgentPlan(agentPlan, catalogById, 'label')   // agent.run_agent output -> what the renderer draws
<RoomScene room={plan.room} items={items} selected={slot} onSelect={setSlot} />
```

- `room`: the same measurements `fit.options.room(...)` takes. Optional `ceiling_in`, `door_wall`, `door_offset_in`.
- `items`: one `{ slot, product, fit }` per slot. Add `placement` to position an item yourself; without it
  the renderer places items by a rule of thumb (`layout.ts`). That placement is not a fit check.
- The parent element needs a size; the canvas fills it.

## Run

```bash
cd web && npm install && npm run dev      # http://localhost:5173/harness
```

The page at `/harness` is a **test harness** for the renderer, not the app's UI. Its plan picker draws the agent's runs in
`contracts/` and a fit-only demo run (`python3 scripts/demo_plan.py` writes `public/demo-plan.json`).

## Product models (image → 3D)

`public/models/index.json` lists products that have a 3D model. Each was generated from the product's main
IKEA photo by Hyper3D Rodin, then shrunk to about 1 MB. A product without a model is drawn as a simple shape.

```bash
python3 scripts/make_model.py <product_id>                 # one product
python3 scripts/make_model.py --plan contracts/plan.live.json   # everything a plan uses (rugs skipped)
```

Needs `HYPER3D_API_KEY` in `.env` (0.5 credits per model) and Blender for the shrink step. Raw downloads are
cached in `.cache/models_raw/` (gitignored), so re-running does not pay twice.

Honesty rules the renderer follows:
- Every model is stretched to the product's **listed** size, and the verdict outline is always the listed size,
  so the picture cannot disagree with the fit maths.
- The label on a model says it is AI-generated from the IKEA photo and scaled to the listed size.
- `stretch_w_d_h` in `index.json` records how far the generated shape's own proportions were from the listed
  size. Thin, tall items (floor lamps) are the weak case.

## The scanned room

`<RoomScene scan={{ url, corner_m, ceiling_in }} />` draws a scan of the real room instead of the box built from
measurements. `python3 scripts/scan_align.py` finds the floor and wall planes in `assets/room_scan_geometry.glb`
and writes `assets/room_scan_geometry.align.json`; `corner_m` is the room's back-left floor corner from that file.
The harness turns the scan on for `plan.room_scan.json`. `?clean` hides the harness panel for screenshots.
