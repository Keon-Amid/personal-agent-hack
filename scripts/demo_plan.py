"""Write web/public/demo-plan.json: a real fit run the 3D room view can draw before the agent exists.

Every verdict and every line of fit maths comes from fit.options (alistair's module) run on the real
catalog in data/products.json. Two things here are NOT real and are listed in the file's "stubbed" field:
  - the room measurements are typed in as arguments (no photo estimate yet)
  - the pick per slot is a simple rule (first best-value option), not the agent's choice

Run from the repo root:
  python3 scripts/demo_plan.py
  python3 scripts/demo_plan.py --wall 132 --wall-error 0 --depth 144 --depth-error 0
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fit import FITS, UNSURE, measurement  # noqa: E402
from fit.options import options, room  # noqa: E402

SLOTS = ["sofa", "armchair", "coffee_table", "rug", "floor_lamp", "tv_bench", "side_table", "bookcase"]
PRODUCT_KEYS = ["id", "name", "category", "price_usd", "dims_in", "color", "image_url", "source_url",
                "rating", "review_count"]
MAX_OTHERS = 6


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wall", type=float, default=89.0, help="wall the furniture goes against, inches")
    ap.add_argument("--wall-error", type=float, default=1.5)
    ap.add_argument("--depth", type=float, default=150.0, help="room depth, inches")
    ap.add_argument("--depth-error", type=float, default=4.0)
    ap.add_argument("--door-width", type=float, default=32.0)
    ap.add_argument("--door-height", type=float, default=80.0)
    ap.add_argument("--ceiling", type=float, default=96.0)
    ap.add_argument("--out", default=str(ROOT / "web" / "public" / "demo-plan.json"))
    a = ap.parse_args()

    def m(value: float, error: float) -> dict:
        return measurement(value, error, "estimated:door" if error > 0 else "user")

    rm = room(m(a.wall, a.wall_error), m(a.depth, a.depth_error),
              measurement(a.door_width), measurement(a.door_height))
    catalog = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))["products"]
    by_id = {p["id"]: p for p in catalog}

    def candidate(o: dict) -> dict:
        p = by_id[o["id"]]
        return {"product": {k: p.get(k) for k in PRODUCT_KEYS}, "fit": o["fit"],
                "fit_results": o["fit_results"], "why": o["why"], "best_value": o["best_value"]}

    items = []
    for slot in SLOTS:
        opts = options(catalog, slot, rm)
        if not opts:
            continue
        pick = (next((o for o in opts if o["best_value"]), None)
                or next((o for o in opts if o["fit"] == FITS), None)
                or next((o for o in opts if o["fit"] == UNSURE), None)
                or opts[0])
        others = [o for o in opts if o is not pick]
        # show the ones that do not fit first: those are the interesting ones to try in the room
        others.sort(key=lambda o: (o["fit"] == FITS, o["price_usd"] is None, o["price_usd"] or 0))
        items.append({"slot": slot, **candidate(pick), "others": [candidate(o) for o in others[:MAX_OTHERS]]})

    plan = {
        "about": "Demo plan for the 3D room view. Verdicts and maths are a real fit.options run on data/products.json.",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "scripts/demo_plan.py",
        "stubbed": [
            "Room measurements are typed in (script arguments), not estimated from a photo.",
            "The pick in each slot is the first best-value option, not the agent's choice.",
        ],
        "room": {**rm, "ceiling_in": a.ceiling, "door_wall": "right",
                 "door_offset_in": max(0.0, a.depth - a.door_width - 10.0)},
        "items": items,
    }
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(items)} slots)")
    for it in items:
        bad = sum(1 for o in it["others"] if o["fit"] != FITS)
        print(f'  {it["slot"]:13} {it["fit"]:7} {it["product"]["name"][:44]:44} others: {len(it["others"])} ({bad} do not fit)')


if __name__ == "__main__":
    main()
