"""Fill a real IKEA bag with an approved plan's cart, check it, and leave the person at IKEA's checkout.

    .venv/bin/pip install playwright        # once; drives the Google Chrome already on this laptop
    .venv/bin/python scripts/ikea_checkout.py <plan_id> [--server http://localhost:8000]

Anyone on the team can run this; it does what the browser agent did by hand:
1. reads the plan's cart from the server (GET /api/plan/{id}),
2. opens a visible Chrome window (its own profile in .cache/ikea-browser, so the bag survives between runs),
3. adds only what is missing (agent.bag_reconcile.add_plan) with scripts/ikea_bag.js addToBag(),
4. reads the bag back (readBag()) and posts it to POST /api/plan/{id}/bag, which checks items and money and
   writes the result to the audit trail (the app's cart shows "Your IKEA bag matches this cart"),
5. leaves the window on ikea.com's bag page. Nothing is bought: the person checks out and pays there.
No login, no payment details, no form is submitted by this script.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from agent.bag_reconcile import add_plan, normalize_item_no  # noqa: E402

JS = (REPO / "scripts" / "ikea_bag.js").read_text()
BAG_URL = "https://www.ikea.com/us/en/shoppingcart/"
PROFILE = REPO / ".cache" / "ikea-browser"


def _http(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def selection_for(plan: dict) -> list[dict]:
    """The cart as bag_reconcile wants it: one of each cart item, by IKEA article number."""
    catalog = {p["id"]: p for p in json.loads((REPO / "data" / "products.json").read_text())["products"]}
    sel = []
    for c in plan["cart"].get("items") or []:
        art = (catalog.get(c["product_id"]) or {}).get("article_number")
        if not art:
            raise SystemExit(f"no IKEA article number for {c['product_id']}")
        sel.append({"item_no": art, "qty": 1, "price_usd": c.get("price_usd"), "name": c.get("name")})
    return sel


def call(page, expr: str):
    """Run one of ikea_bag.js's functions in the page (the file only defines functions)."""
    return page.evaluate(f"async () => {{ {JS}\n return await {expr}; }}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_id")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--close", action="store_true", help="close the browser at the end (default: leave it open)")
    a = ap.parse_args()

    code, plan = _http("GET", f"{a.server}/api/plan/{a.plan_id}")
    if code != 200:
        raise SystemExit(f"GET plan {a.plan_id}: HTTP {code} {plan}")
    if not (plan["cart"].get("approval") or {}).get("approved"):
        raise SystemExit("approve the cart in the app first (Review the cart -> Approve); nothing was added")
    sel = selection_for(plan)
    print(f"cart: {len(sel)} items, ${plan['cart']['total_usd']:.2f}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        PROFILE.mkdir(parents=True, exist_ok=True)
        ctx = pw.chromium.launch_persistent_context(str(PROFILE), channel="chrome", headless=False,
                                                    viewport={"width": 1280, "height": 860})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BAG_URL, wait_until="domcontentloaded")
        before = call(page, "readBag()")
        todo = add_plan(sel, before)
        print(f"already in the bag: {len(before.get('lines') or [])} lines; adding {len(todo)}")
        for t in todo:
            no = normalize_item_no(t["item_no"]).replace(".", "")
            page.goto(f"https://www.ikea.com/us/en/p/-{no}/", wait_until="load")
            res = call(page, f"addToBag({int(t['qty'])})")
            print(f"  add {t['item_no']} x{t['qty']}: {'ok' if res.get('ok') else 'FAILED ' + str(res.get('error'))}")
        page.goto(BAG_URL, wait_until="domcontentloaded")
        bag = call(page, "readBag()")
        code, out = _http("POST", f"{a.server}/api/plan/{a.plan_id}/bag", bag)
        verdict = ((out.get("cart") or {}).get("bag") or {}).get("verdict") if code == 200 else None
        print(f"bag check: HTTP {code} verdict={verdict} bag_total={((out.get('cart') or {}).get('bag') or {}).get('bag_total_usd')}"
              + ("" if code == 200 else f" {out}"))
        if a.close:
            ctx.close()
        else:
            print("Your IKEA bag is open in the Chrome window: check out and pay there. Press Enter here to close it.")
            try:
                input()
            except EOFError:
                pass
            ctx.close()
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
