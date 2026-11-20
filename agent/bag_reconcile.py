"""Check a real IKEA bag against what the agent picked: items AND money.

The bag is read in the browser by `scripts/ikea_bag.js` (`readBag()`), which returns
`{"lines": [{"itemNo", "name", "qty", "lineTotal"}], "productsTotal"}`. This module
compares that to the agent's selection and says PASS only when every picked item is
in the bag at the right quantity, nothing extra is there, and the bag's total matches
the price the agent quoted (and fits the budget, if one is given).

Found live on ikea.com 2026-11-20 (docs/ikea-cart-browser.md):
- IKEA writes article numbers as "206.316.63" in the bag and "20631663" in the
  catalog/search API. Compare digits only.
- The search API can return the IKEA Family member price (BILLY: $65), while a guest
  bag charges the regular price ($79). The bag's total is the truth; a difference is
  reported per line so it can go in the audit trail.
"""
from __future__ import annotations

import re


def normalize_item_no(item_no: str | int) -> str:
    """'206.316.63', 's20631663', 20631663 -> '20631663'."""
    return re.sub(r"\D", "", str(item_no))


def _money(v) -> float | None:
    if v is None or v == "":
        return None
    return round(float(str(v).replace("$", "").replace(",", "").strip()), 2)


def reconcile(selection: list[dict], bag: dict, budget_usd: float | None = None) -> dict:
    """Compare the agent's selection to the bag.

    selection: [{"item_no", "qty", "price_usd"}]  (price_usd = per-unit price the agent quoted)
    bag:       readBag() output.
    Returns {"verdict": "PASS"|"FAIL", "item_diff": [...], "price_deltas": [...],
             "expected_total_usd", "bag_total_usd", "over_budget": bool, "reasons": [...]}.
    """
    expected = {}
    quoted = {}
    for s in selection:
        k = normalize_item_no(s["item_no"])
        expected[k] = expected.get(k, 0) + int(s["qty"])
        quoted[k] = _money(s.get("price_usd"))

    got = {}
    line_totals = {}
    for line in bag.get("lines", []):
        k = normalize_item_no(line.get("itemNo", ""))
        got[k] = got.get(k, 0) + int(line.get("qty", 0))
        if line.get("lineTotal") is not None:
            line_totals[k] = _money(line["lineTotal"])

    item_diff = []
    for k, qty in expected.items():
        if got.get(k, 0) != qty:
            item_diff.append({"item_no": k, "expected_qty": qty, "bag_qty": got.get(k, 0)})
    for k, qty in got.items():
        if k not in expected:
            item_diff.append({"item_no": k, "expected_qty": 0, "bag_qty": qty, "unexpected": True})

    price_deltas = []
    for k, qty in expected.items():
        if k in line_totals and quoted.get(k) is not None:
            quoted_line = round(quoted[k] * qty, 2)
            if abs(line_totals[k] - quoted_line) > 0.005:
                price_deltas.append({"item_no": k, "quoted_usd": quoted_line,
                                     "bag_usd": line_totals[k],
                                     "delta_usd": round(line_totals[k] - quoted_line, 2)})

    expected_total = round(sum((quoted.get(k) or 0) * q for k, q in expected.items()), 2)
    bag_total = _money(bag.get("productsTotal"))
    over_budget = budget_usd is not None and bag_total is not None and bag_total > budget_usd + 0.005

    reasons = []
    if item_diff:
        reasons.append(f"{len(item_diff)} item line(s) differ from the selection")
    if bag_total is None:
        reasons.append("bag total could not be read")
    elif abs(bag_total - expected_total) > 0.005:
        reasons.append(f"bag total ${bag_total:.2f} != quoted ${expected_total:.2f}")
    if over_budget:
        reasons.append(f"bag total ${bag_total:.2f} is over the ${budget_usd:.2f} budget")

    return {"verdict": "PASS" if not reasons else "FAIL", "item_diff": item_diff,
            "price_deltas": price_deltas, "expected_total_usd": expected_total,
            "bag_total_usd": bag_total, "over_budget": over_budget, "reasons": reasons}


def add_plan(selection: list[dict], bag: dict) -> list[dict]:
    """What to add so the bag matches the selection. Adding an item already in the bag
    increases its quantity, so add only the difference (never re-add the whole list)."""
    have = {}
    for line in bag.get("lines", []):
        k = normalize_item_no(line.get("itemNo", ""))
        have[k] = have.get(k, 0) + int(line.get("qty", 0))
    want = {}
    for s in selection:
        k = normalize_item_no(s["item_no"])
        want[k] = want.get(k, 0) + int(s["qty"])
    return [{"item_no": k, "qty": q - have.get(k, 0)} for k, q in want.items() if q > have.get(k, 0)]
