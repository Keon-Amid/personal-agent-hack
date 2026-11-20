# web/ — the 3D room renderer

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
cd web && npm install && npm run dev      # http://localhost:5173
```

The page is a **test harness** for the renderer, not the app's UI. Its plan picker draws the agent's runs in
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
