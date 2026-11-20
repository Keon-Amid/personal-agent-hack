"""Turn a pick into claims Senso will actually check.

Tested live (see CONTRACT.md, Senso section): Senso's kb_accuracy only scores claims it reads as being about
our org, and it confuses products that share a name. So every claim here
  - names the product with its IKEA article number and colour, and
  - states the fact under the team rule it supports ("Under the walkway rule, ...").
Room measurements aren't in Senso, so claims only state product facts and rules; the fit verdict itself comes
from fit/ (the math), and the claim text says which rule it relates to.

    claims_for(product, fit_results) -> [{"rule", "text"}]
    claim_text(product, fit_results) -> one paragraph to send to POST /org/evals/text
"""
from __future__ import annotations


def _in(v: float) -> str:
    return f"{v:g} inches"


RULES = {  # wording from the team's "Room Furnisher clearance rules" doc in Senso
    "wall": "Under our wall-fit rule, a piece placed against a wall must be no wider than that wall.",
    "walkway": "Under our walkway rule, at least 36 inches of clear walkway is kept in front of any furniture "
               "placed against a wall.",
    "doorway": "Under our doorway rule, every shipping box (package) must fit through the room's doorway.",
    "rug": "Under our rug rule, a rug is kept at least 6 inches from every wall.",
}


def claims_for(p: dict, fit_results: list[dict]) -> list[dict]:
    """One claim per rule: the rule as our policy, then the product fact as "Our catalog lists ...".
    Tested live: that phrasing is scored (true -> grounded, a wrong number -> contradicts_kb); bare product facts
    are not scored at all, and mixing fact and rule in one sentence comes back unsupported_by_kb."""
    d = p["dims_in"]
    item = f'the {p["name"]}, IKEA article {p["article_number"]},'
    checks = {r["check"] for r in fit_results}
    out = []
    if "wall" in checks:
        out.append({"rule": "wall", "text": f"{RULES['wall']} Our catalog lists {item} as {_in(d['w'])} wide."})
    if "floor" in checks:
        out.append({"rule": "walkway", "text": f"{RULES['walkway']} Our catalog lists {item} as {_in(d['d'])} deep."})
    if {"rug_width", "rug_depth"} & checks:
        out.append({"rule": "rug", "text": f"{RULES['rug']} Our catalog lists {item} as {_in(d['w'])} wide "
                                           f"and {_in(d['d'])} long."})
    if {"doorway_width", "doorway_height"} & checks:
        boxes = p.get("packages_in")
        if boxes:
            parts = "; ".join(f'box {i} as {_in(b["w"])} wide, {_in(b["d"])} long and {_in(b["h"])} high'
                              for i, b in enumerate(boxes, 1))
            out.append({"rule": "doorway", "text": f"{RULES['doorway']} Our catalog lists {item} as shipping in "
                                                   f"{len(boxes)} box(es): {parts}."})
    if p.get("price_usd") is not None:
        out.append({"rule": "price", "text": f"Our catalog lists {item} at ${p['price_usd']:g} on the IKEA US page."})
    return out


def claim_text(p: dict, fit_results: list[dict]) -> str:
    return " ".join(c["text"] for c in claims_for(p, fit_results))
