"""Pick one product for a slot: Superlinked's style ranking decides the order, our fit checks decide what's allowed.

Walk down the style ranking (best match first). The first product that fits (and is within budget, if given)
is picked. Every product ranked above it is recorded as rejected, with the reason. That gives the audit trail
its key moment: "style match #1 KIVIK rejected: width 89.75 in > 88 in".

Input: `fit.options(...)` output (fit + price + rating) and `data.sie.style_match(...)` output (style ranks).
No network calls here; the caller runs style_match.
"""
from __future__ import annotations

from .checks import FITS


def pick(opts: list[dict], style: dict, budget_usd: float | None = None) -> dict:
    by_id = {o["id"]: o for o in opts}
    src = style["source"]
    rejected, chosen = [], None
    for s in style["ranked"]:
        o = by_id.get(s["id"])
        if o is None:
            continue
        style_why = (f'style #{s["style_rank"]} of {len(style["ranked"])} '
                     f'(photo #{s["photo_rank"]} {s["photo_score"]:.3f}, text #{s["text_rank"]} {s["text_score"]:.3f})')
        if o["fit"] != FITS:
            reason = o["why"]
        elif o["price_usd"] is None:
            reason = "no price on the IKEA page"
        elif budget_usd is not None and o["price_usd"] > budget_usd:
            reason = f'over budget: ${o["price_usd"]:g} > ${budget_usd:g}'
        else:
            chosen = {**o, "style": s, "style_why": style_why}
            break
        rejected.append({"id": o["id"], "name": o["name"], "style_rank": s["style_rank"],
                         "status": o["fit"] if o["fit"] != FITS else "rejected", "why": reason,
                         "style_why": style_why})
    records = [{"step": "rank", "item_slot": style["category"], "input": style["style_text"],
                "source": {**src, "detected_style": (style["detected_style"] or [None])[0]},
                "decision": "ranked", "why": f'{len(style["ranked"])} {style["category"]} products ranked by style'}]
    for r in rejected:
        records.append({"step": "pick", "item_slot": style["category"], "product_id": r["id"],
                        "source": {"kind": "fit", **src}, "decision": "rejected", "status": r["status"],
                        "why": f'{r["style_why"]}; {r["why"]}'})
    if chosen:
        value = "best value" if chosen["best_value"] else "not the best value"
        records.append({"step": "pick", "item_slot": style["category"], "product_id": chosen["id"],
                        "source": {"kind": "superlinked", **src, "url": chosen["source_url"]},
                        "decision": "picked", "status": "fits",
                        "why": f'{chosen["style_why"]}; fits; ${chosen["price_usd"]:g}, '
                               f'{chosen["rating"]}★ ({chosen["review_count"]} reviews), {value}'})
    return {"slot": style["category"], "picked": chosen, "rejected": rejected, "audit": records}
