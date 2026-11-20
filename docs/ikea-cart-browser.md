# A real IKEA bag, filled by the browser and checked

Tested live on ikea.com/us/en, 2026-11-20 (brendan). Today `POST /api/plan/{id}/approve` returns a
shopping list (`mocked_checkout: true`). This is the tested path to a **real IKEA bag** instead: the
agent fills it, reads it back, and checks it before the person checks out. Nothing is bought.

## What was tried

| Route | Result |
|---|---|
| Unofficial `ikea-api` (archived) cart | ❌ Guest token: `401 "APIM Gateway Authorization Error"` from `api.ingka.ikea.com/guest/token`. Its hard-coded client ID is rejected. Search still works. |
| Browser: product page by article number → "Add to bag" → read the bag page | ✅ Works. No bot challenge, no login. |

## The flow (`scripts/ikea_bag.js` + `agent/bag_reconcile.py`)

1. `add_plan(selection, current_bag)`: add only what is missing (adding again increases quantity).
2. Per item: open `https://www.ikea.com/us/en/p/-<itemNo>/` (redirects to the exact product page) → `addToBag(qty)`.
3. Open `https://www.ikea.com/us/en/shoppingcart/` → `readBag()` returns `{lines:[{itemNo, name, qty, lineTotal}], productsTotal}`.
4. `reconcile(selection, bag, budget_usd)` → PASS only if every item and quantity matches, nothing extra,
   and the bag total equals the quoted total (and fits the budget). Each part goes in the audit trail.

## Live run (3 products)

Expected KALLAX `20631663` ×2, LACK `80104268` ×3, BILLY `20522046` ×1. Bag counter went 2 → 5 → 6.
`readBag()` + reconcile: **items `diff: []`** (all present, right quantities), **total `289.95` vs quoted `275.95` → FAIL**.

The $14.00 is BILLY: the search API gave the **IKEA Family member price ($65)**; a guest bag charges
**$79**. The approve route's live re-check reads the product page; check that it reads the regular price,
not the Family price. Use the bag's total as the price the person sees.

## Gotchas

- Article numbers are `206.316.63` in the bag and `20631663` in the catalog: compare digits only.
- `get_page_text` on the bag page returns nothing; read it with the script.
- Not yet tested: an out-of-stock item (`addToBag` returns `ok:false` if no "Add to bag" button), and speed when automated end to end.

## One command for anyone on the team (no Claude session needed)
```sh
.venv/bin/pip install -r server/requirements.txt     # includes playwright; uses the Google Chrome already installed
.venv/bin/python scripts/ikea_checkout.py <plan_id>  # after Approve in the app
```
Opens a visible Chrome window (own profile in `.cache/ikea-browser`, so the bag survives), adds only what is missing,
reads the bag back, posts it to `POST /api/plan/{id}/bag` (the app's cart then shows the verdict), and leaves the window
on IKEA's bag page for the person to check out. Nothing is bought; no login; no form is submitted.
Live 2026-11-20 on plan 739e77ac7237 (scanned room, $900 budget): 5 items, IKEA bag total $887.97 = cart, verdict PASS.
The bag is per browser profile: it shows in that Chrome window, not in your everyday Chrome.
