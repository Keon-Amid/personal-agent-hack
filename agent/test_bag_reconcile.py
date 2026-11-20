"""Fixtures are the real readBag() output from the live ikea.com run on 2026-11-20."""
from agent.bag_reconcile import add_plan, normalize_item_no, reconcile

SELECTION = [
    {"item_no": "20631663", "qty": 2, "price_usd": 79.99},   # KALLAX
    {"item_no": "80104268", "qty": 3, "price_usd": 16.99},   # LACK
    {"item_no": "20522046", "qty": 1, "price_usd": 65.00},   # BILLY: search API gave the Family price
]
LIVE_BAG = {
    "lines": [
        {"itemNo": "205.220.46", "name": "BILLY, white", "qty": 1, "lineTotal": "79.00"},
        {"itemNo": "801.042.68", "name": "LACK, black-brown", "qty": 3, "lineTotal": "50.97"},
        {"itemNo": "206.316.63", "name": "KALLAX, white", "qty": 2, "lineTotal": "159.98"},
    ],
    "productsTotal": "289.95",
}


def test_normalize_item_no():
    assert normalize_item_no("206.316.63") == "20631663"
    assert normalize_item_no("s20631663") == "20631663"
    assert normalize_item_no(20631663) == "20631663"


def test_live_bag_items_match_but_price_check_fails():
    r = reconcile(SELECTION, LIVE_BAG)
    assert r["item_diff"] == []
    assert r["verdict"] == "FAIL"
    assert r["expected_total_usd"] == 275.95 and r["bag_total_usd"] == 289.95
    assert r["price_deltas"] == [{"item_no": "20522046", "quoted_usd": 65.0, "bag_usd": 79.0, "delta_usd": 14.0}]


def test_passes_with_bag_prices():
    sel = [dict(s, price_usd=79.00) if s["item_no"] == "20522046" else s for s in SELECTION]
    r = reconcile(sel, LIVE_BAG, budget_usd=300)
    assert r["verdict"] == "PASS", r["reasons"]


def test_missing_and_unexpected_items_and_budget():
    bag = {"lines": LIVE_BAG["lines"][1:] + [{"itemNo": "123.456.78", "qty": 1}], "productsTotal": "210.95"}
    r = reconcile(SELECTION, bag, budget_usd=200)
    assert {"item_no": "20522046", "expected_qty": 1, "bag_qty": 0} in r["item_diff"]
    assert any(d.get("unexpected") for d in r["item_diff"])
    assert r["over_budget"] and r["verdict"] == "FAIL"


def test_add_plan_adds_only_the_difference():
    bag = {"lines": [{"itemNo": "206.316.63", "qty": 2}], "productsTotal": "159.98"}
    assert add_plan(SELECTION, bag) == [{"item_no": "80104268", "qty": 3}, {"item_no": "20522046", "qty": 1}]
