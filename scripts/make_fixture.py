"""Generate contracts/plan.example.json (roadmap package A1 shape) from a REAL run of what's on main.

Per slot: Superlinked style_match (one shared room analysis) -> fit.options -> fit.pick -> fit.claims -> one live
Senso fact-check of the picked item's claims. Nothing hand-typed: every number comes from data/products.json,
the fit math, Superlinked or Senso. The `why` line is built from those facts (Brendan's agent will replace it with
Claude's sentence). Needs SIE_API_KEY and SENSO_API_KEY.

    python3 scripts/make_fixture.py [--no-senso]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import senso_kb  # noqa: E402
from data import sie  # noqa: E402
from fit import measurement  # noqa: E402
from fit.claims import claim_text  # noqa: E402
from fit.options import options, room  # noqa: E402
from fit.pick import pick  # noqa: E402

SLOTS = ["sofa", "armchair", "coffee_table", "rug", "floor_lamp"]
# A real IKEA room photo (from the KIVIK product page), standing in for the person's photo.
PHOTO_URL = "https://www.ikea.com/us/en/images/products/kivik-sofa-tibbleby-beige-gray__1399650_ph191619_s5.jpg"
BUDGET_PER_SLOT = 600


def senso_check(text: str) -> dict:
    code, out = senso_kb._req("POST", "/org/evals/text", {"text": text, "wait": True})
    if code != 200:
        return {"check_id": None, "error": f"HTTP {code}", "claims": []}
    ev = out.get("evidence_chunks") or []
    quote = (ev[0].get("text") or "")[:300] if ev else None
    return {
        "check_id": out.get("eval_run_id"),
        "scored": out.get("claims_scored"), "total": out.get("claims_total"),
        "claims": [{"claim": c["claim_text"],
                    "verdict": {True: "verified", False: "conflict"}.get(c.get("passed"), "unsupported"),
                    "bucket": c.get("bucket")} for c in out.get("claims") or []],
        "quote": quote,
    }


def main(use_senso: bool = True) -> dict:
    products = json.loads((ROOT / "data/products.json").read_text())["products"]
    by_id = {p["id"]: p for p in products}
    emb = json.loads((ROOT / "data/style_embeddings.json").read_text())
    rm = room(measurement(88, 4, "estimated:door"), measurement(150, 6, "estimated:door"),
              measurement(30, 0, "user"), measurement(80, 0, "user"))
    R = sie.analyze_room(room_photo=sie.fetch_image(PHOTO_URL))
    items, audit = [], []
    for slot in SLOTS:
        style = sie.style_match(products, slot, emb, room=R)
        r = pick(options(products, slot, rm), style, budget_usd=BUDGET_PER_SLOT)
        audit += r["audit"]
        o = r["picked"]
        if not o:
            continue
        p = by_id[o["id"]]
        senso = senso_check(claim_text(p, o["fit_results"])) if use_senso else None
        if senso:
            audit.append({"step": "senso_check", "item_slot": slot, "product_id": p["id"],
                          "source": {"kind": "senso", "senso_check_id": senso["check_id"], "passage": senso["quote"]},
                          "decision": "picked",
                          "status": "verified" if senso["claims"] and all(c["verdict"] == "verified" for c in senso["claims"])
                          else "unsupported",
                          "why": f'Senso: {sum(c["verdict"] == "verified" for c in senso["claims"])} of '
                                 f'{len(senso["claims"])} claims verified'})
        items.append({
            "slot": slot, "product_id": p["id"], "name": p["name"], "price_usd": p["price_usd"],
            "dims_in": p["dims_in"], "image_url": p["image_url"], "source_url": p["source_url"],
            "style": {"rank": o["style"]["style_rank"], "photo_score": o["style"]["photo_score"],
                      "text_score": o["style"]["text_score"], "labels": o["style"].get("product_styles", [])},
            "fit": {"verdict": o["fit"], "results": o["fit_results"]},
            "senso": senso,
            "why": o["style_why"] + "; fits; " + ("best value" if o["best_value"] else "not the best value"),
            "rejected": [{"product_id": x["id"], "name": x["name"], "status": x["status"], "why": x["why"]}
                         for x in r["rejected"]],
        })
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for a in audit:
        a.setdefault("ts", now)
    return {
        "plan_id": "demo-1",
        "generated": {"at": now, "by": "scripts/make_fixture.py (real run: Superlinked + fit + Senso)",
                      "note": "why lines are built from facts; the agent will write the final sentence"},
        "room": {**rm, "photo_url": PHOTO_URL, "detected_style": R["detected_style"][:3] if R["detected_style"] else None},
        "items": items,
        "cart": {"total_usd": round(sum(i["price_usd"] for i in items), 2),
                 "delivery_note": "IKEA home delivery from $29 ($19 with IKEA Family); no delivery date available",
                 "no_purchase": True},
        "audit": audit,
    }


if __name__ == "__main__":
    plan = main(use_senso="--no-senso" not in sys.argv)
    out = ROOT / "contracts" / "plan.example.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    print(f"wrote {out.relative_to(ROOT)}: {len(plan['items'])} items, ${plan['cart']['total_usd']}, "
          f"{len(plan['audit'])} audit records")
