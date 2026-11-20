"""Alternatives per slot for each recorded plan, straight from fit.options (the real fit math).

    python3 web/scripts/make_options.py        # run from the repo root

Writes web/src/fixtures/options.<plan_id>.json = {slot: [Option]} for every contracts/plan.*.json that has items.
The UI reads these in replay mode for the "Alternatives that fit" chart. Nothing is typed by hand.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from fit.options import options, room  # noqa: E402

products = json.load(open(os.path.join(ROOT, "data", "products.json")))["products"]
out_dir = os.path.join(ROOT, "web", "src", "fixtures")
os.makedirs(out_dir, exist_ok=True)

for path in sorted(glob.glob(os.path.join(ROOT, "contracts", "plan.*.json"))):
    plan = json.load(open(path))
    if not plan.get("items") or "plan_id" not in plan or "wall" not in plan.get("room", {}):
        continue
    r = plan["room"]
    rm = room(r["wall"], r["depth"], r["door_width"], r["door_height"])
    by_slot = {it["slot"]: options(products, it["slot"], rm) for it in plan["items"]}
    dest = os.path.join(out_dir, f"options.{plan['plan_id']}.json")
    json.dump(by_slot, open(dest, "w"), indent=1)
    print(os.path.relpath(dest, ROOT), {k: len(v) for k, v in by_slot.items()})
