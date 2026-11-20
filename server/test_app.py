"""Offline tests for the HTTP API: run_agent and the Senso-calling tools are replaced with fakes."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from agent import store
from server import app as srv


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_FURNISHER_PLANS_DIR", str(tmp_path))
    srv.RUNS.clear()
    # Offline: the live IKEA re-check in approve sees the catalog price unless a test says otherwise.
    by_url = {p["source_url"]: p for p in srv._products().values()}
    monkeypatch.setattr(srv, "_fetch_live", lambda url, cat: {"price_usd": by_url[url]["price_usd"]})
    return TestClient(srv.app)


def _wait(client, pid, status, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        p = client.get(f"/api/plan/{pid}").json()
        if p["run"]["status"] == status:
            return p
        time.sleep(0.02)
    raise AssertionError(f"plan {pid} never reached {status}")


def test_start_returns_at_once_and_plan_grows(client, monkeypatch):
    gate = threading.Event()
    seen = {}

    def fake_run_agent(room_input, photo_b64=None, style_text=None, budget_usd=None, on_event=None, plan_id=None, **kw):
        seen.update(room=room_input, style_text=style_text, budget=budget_usd)
        store.new_plan(plan_id=plan_id)
        store.append_audit(plan_id, {"step": "agent", "decision": "start", "why": "", "source": {"kind": "template"}})
        gate.wait(5)
        store.update(plan_id, lambda p: p["items"].append({"slot": "sofa", "name": "GLOSTAD"}))

    monkeypatch.setattr(srv.agent_mod, "run_agent", fake_run_agent)
    r = client.post("/api/plan", json={"room": {"wall": 88, "depth": 120, "door_width": 32, "door_height": 80},
                                       "style_text": "warm minimal", "budget_usd": 500})
    assert r.status_code == 200
    pid = r.json()["plan_id"]
    p = client.get(f"/api/plan/{pid}").json()
    assert p["run"]["status"] == "running" and p["items"] == []
    gate.set()
    p = _wait(client, pid, "done")
    assert p["items"][0]["name"] == "GLOSTAD" and p["audit"][0]["step"] == "agent"
    assert "state" not in p
    assert seen == {"room": {"wall": 88, "depth": 120, "door_width": 32, "door_height": 80},
                    "style_text": "warm minimal", "budget": 500}


def test_quiz_answers_fill_style_and_budget(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(srv.agent_mod, "run_agent",
                        lambda room, photo_b64=None, style_text=None, budget_usd=None, plan_id=None, **kw:
                        seen.update(style_text=style_text, budget=budget_usd))
    answers = {"q1_mood": "light", "q2_touch": "linen_oak", "q3_never": "loft", "q4_life": "kids_pets",
               "q5_budget": "mid"}
    pid = client.post("/api/plan", json={"room": {"wall": 88}, "quiz_answers": answers}).json()["plan_id"]
    p = _wait(client, pid, "done")
    assert seen["style_text"].startswith("scandinavian living room") and seen["budget"] == 500
    assert p["run"]["persona"]["style"] == "scandinavian"


def test_agent_error_reaches_the_browser(client, monkeypatch):
    def boom(*a, **k):
        raise srv.agent_mod.AgentError("Claude Code is not on PATH")
    monkeypatch.setattr(srv.agent_mod, "run_agent", boom)
    pid = client.post("/api/plan", json={"room": {"wall": 88}}).json()["plan_id"]
    p = _wait(client, pid, "error")
    assert "not on PATH" in p["run"]["error"]


def test_bad_requests(client):
    assert client.post("/api/plan", json={}).status_code == 400
    assert client.get("/api/plan/nope").status_code == 404
    assert client.post("/api/quiz/score", json={"answers": {"q1_mood": "light"}}).status_code == 400


def test_swap_runs_swap_senso_cart_in_order(client, monkeypatch):
    pid = store.new_plan()["plan_id"]
    calls = []
    monkeypatch.setattr(srv.tools, "swap", lambda p, s: calls.append(("swap", s)) or {"ok": True, "picked": {"name": "X"}})
    monkeypatch.setattr(srv.tools, "senso_check", lambda p, s: calls.append(("senso", s)) or {"ok": True})
    monkeypatch.setattr(srv.tools, "cart_add", lambda p, s, why: calls.append(("cart", why)) or {"ok": True})
    r = client.post(f"/api/plan/{pid}/swap", json={"slot": "sofa"})
    assert r.status_code == 200
    assert calls == [("swap", "sofa"), ("senso", "sofa"), ("cart", "")]
    assert client.post(f"/api/plan/{pid}/swap", json={"slot": "piano"}).status_code == 400


def test_quiz_endpoints_and_health(client):
    assert len(client.get("/api/quiz").json()["questions"]) == 5
    r = client.post("/api/quiz/score", json={"answers": {
        "q1_mood": "moody", "q2_touch": "leather_metal", "q3_never": "formal", "q4_life": "hosting",
        "q5_budget": "comfortable"}}).json()
    assert r["style"] == "dark modern" and "summary" in r["catalog_support"]
    h = client.get("/api/health").json()
    assert set(h) == {"claude_code", "superlinked_key", "senso_key", "runs"}


def _plan_with_cart(product_ids):
    import json
    from pathlib import Path
    cat = {p["id"]: p for p in json.loads((Path(srv.REPO) / "data" / "products.json").read_text())["products"]}
    pid = store.new_plan()["plan_id"]

    def fill(p):
        for i in product_ids:
            c = cat[i]
            p["cart"]["items"].append({"product_id": i, "name": c["name"], "price_usd": c["price_usd"],
                                       "source_url": c["source_url"]})
        p["cart"]["total_usd"] = round(sum(c["price_usd"] or 0 for c in p["cart"]["items"]), 2)
    store.update(pid, fill)
    return pid, cat


def test_approve_builds_shopping_list_and_one_audit_record(client):
    real = "ikea-glostad-sofa-knisa-dark-gray-40595942"
    pid, cat = _plan_with_cart([real])
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 200
    p = r.json()
    appr = p["cart"]["approval"]
    assert appr["approved"] is True and appr["item_count"] == 1 and appr["total_usd"] == cat[real]["price_usd"]
    assert appr["approved_at"].endswith("Z") and p["cart"]["no_purchase"] is True
    recs = [a for a in p["audit"] if a.get("status") == "approved"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec["step"] == "cart" and rec["source"] == {"kind": "template"}
    assert rec["decision"] == "cart approved by the person" and "No purchase is made" in rec["why"]
    assert rec["input"] == {"total_usd": cat[real]["price_usd"], "product_ids": [real]}
    assert p["shopping_list"] == [{"name": cat[real]["name"], "article_number": cat[real]["article_number"],
                                   "price_usd": cat[real]["price_usd"], "source_url": cat[real]["source_url"]}]
    assert p["action"] == {"kind": "shopping_list", "mocked_checkout": True,
                           "note": "No order is placed. Open each IKEA link to buy."}
    assert p["run"]["status"] == "done"


def test_approve_twice_is_idempotent(client):
    pid, _ = _plan_with_cart(["ikea-glostad-sofa-knisa-dark-gray-40595942"])
    first = client.post(f"/api/plan/{pid}/approve", json={}).json()
    second = client.post(f"/api/plan/{pid}/approve")
    assert second.status_code == 200
    assert second.json()["cart"]["approval"] == first["cart"]["approval"]
    assert len(second.json()["audit"]) == len(first["audit"])
    assert sum(1 for a in second.json()["audit"] if a.get("status") == "approved") == 1


def test_approve_refuses_empty_running_unknown(client):
    pid = store.new_plan()["plan_id"]
    assert client.post(f"/api/plan/{pid}/approve").status_code == 409
    assert store.get(pid)["audit"] == [] and "approval" not in store.get(pid)["cart"]
    busy, _ = _plan_with_cart(["ikea-glostad-sofa-knisa-dark-gray-40595942"])
    srv._set_run(busy, status="running")
    assert client.post(f"/api/plan/{busy}/approve").status_code == 409
    assert client.post("/api/plan/nope/approve").status_code == 404


def _agent_rec(status, decision):
    return {"step": "agent", "decision": decision, "why": "x", "status": status, "source": {"kind": "template"}}


def test_status_after_restart_comes_from_the_audit_trail(client):
    # RUNS is empty (a fresh process): the plan file's last agent record decides, never a default "done".
    cut, _ = _plan_with_cart(["ikea-glostad-sofa-knisa-dark-gray-40595942"])
    store.append_audit(cut, _agent_rec("started", "start Claude Code agent"))
    store.append_audit(cut, _agent_rec("called", "call pick"))
    p = client.get(f"/api/plan/{cut}").json()
    assert p["run"]["status"] == "interrupted" and "restarted" in p["run"]["error"]
    assert client.post(f"/api/plan/{cut}/approve").status_code == 409
    assert client.post(f"/api/plan/{cut}/swap", json={"slot": "sofa"}).status_code == 409
    assert "approval" not in store.get(cut)["cart"]

    done = store.new_plan()["plan_id"]
    store.append_audit(done, _agent_rec("done", "agent finished"))
    assert client.get(f"/api/plan/{done}").json()["run"] == {"status": "done", "error": None, "persona": None}

    failed = store.new_plan()["plan_id"]
    store.append_audit(failed, _agent_rec("timeout", "stopped: timeout"))
    r = client.get(f"/api/plan/{failed}").json()["run"]
    assert r["status"] == "error" and "timeout" in r["error"]

    # A tool failure mid-run is not the end of the run.
    mid = store.new_plan()["plan_id"]
    store.append_audit(mid, _agent_rec("error", "pick failed"))
    assert client.get(f"/api/plan/{mid}").json()["run"]["status"] == "interrupted"


def test_swap_after_approve_withdraws_approval_and_names_the_person(client, monkeypatch):
    real = "ikea-glostad-sofa-knisa-dark-gray-40595942"
    pid, cat = _plan_with_cart([real])
    assert client.post(f"/api/plan/{pid}/approve").json()["cart"]["approval"]["approved"] is True

    def fake_swap(p, s):
        def drop(plan):
            plan["cart"]["items"] = []
            plan["cart"]["total_usd"] = 0.0
        store.update(p, drop)
        return {"ok": True, "picked": {"name": "Y"}}

    def fake_cart_add(p, s, why):
        assert why == ""
        store.append_audit(p, {"step": "cart", "item_slot": s, "product_id": "other", "source": {"kind": "template"},
                               "decision": "added to cart", "status": "in_cart",
                               "why": "(the agent gave no explanation)"})
        store.update(p, lambda plan: plan["cart"]["items"].append(
            {"product_id": "other", "name": "Y", "price_usd": 10.0, "source_url": None}) or
            plan["cart"].update(total_usd=10.0))
        return {"ok": True}

    monkeypatch.setattr(srv.tools, "swap", fake_swap)
    monkeypatch.setattr(srv.tools, "senso_check", lambda p, s: {"ok": True})
    monkeypatch.setattr(srv.tools, "cart_add", fake_cart_add)
    p = client.post(f"/api/plan/{pid}/swap", json={"slot": "sofa"}).json()
    assert "approval" not in p["cart"]
    by = {a["decision"]: a for a in p["audit"]}
    req = by["swap requested by the person"]
    assert req["step"] == "swap" and req["source"]["requested_by"] == "person" and req["item_slot"] == "sofa"
    wd = by["approval withdrawn: cart changed by swap"]
    assert wd["step"] == "cart" and wd["input"]["previous_approval"]["product_ids"] == [real]
    cart_rec = [a for a in p["audit"] if a.get("status") == "in_cart"][-1]
    assert "agent gave no explanation" not in cart_rec["why"] and "person's swap" in cart_rec["why"]
    assert cart_rec["source"] == {"kind": "template", "requested_by": "person"}

    # Approving again records a fresh approval for the new cart.
    a = client.post(f"/api/plan/{pid}/approve").json()
    assert a["cart"]["approval"]["product_ids"] == ["other"] and a["cart"]["approval"]["total_usd"] == 10.0
    assert sum(1 for x in a["audit"] if x.get("status") == "approved") == 2
    assert [s["name"] for s in a["shopping_list"]] == ["Y"]


def test_approve_again_after_cart_changed_elsewhere_reapproves(client):
    # e.g. the agent's own swap via MCP changed the cart: the stale approval must not be returned as-is.
    a, _ = _plan_with_cart(["ikea-glostad-sofa-knisa-dark-gray-40595942"])
    client.post(f"/api/plan/{a}/approve")
    store.update(a, lambda plan: plan["cart"].update(total_usd=1.0))
    r = client.post(f"/api/plan/{a}/approve").json()
    assert r["cart"]["approval"]["total_usd"] == 1.0
    assert sum(1 for x in r["audit"] if x.get("status") == "approved") == 2


def test_empty_placeholder_has_plan_live_cart_shape(client, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(srv.agent_mod, "run_agent", lambda *a, **k: gate.wait(5))
    pid = client.post("/api/plan", json={"room": {"wall": 88}}).json()["plan_id"]
    p = client.get(f"/api/plan/{pid}").json()
    # Approve before the plan file exists: the run is still going, so 409, not 404.
    status = client.post(f"/api/plan/{pid}/approve").status_code
    gate.set()
    assert p["run"]["status"] == "running" and status == 409
    assert p["cart"]["delivery_note"] == srv.DELIVERY_NOTE
    assert set(p["cart"]) == set(store.new_plan()["cart"])


def test_room_budget_reaches_run_agent(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(srv.agent_mod, "run_agent", lambda *a, **k: seen.update(k))
    pid = client.post("/api/plan", json={"room": {"wall": 88}, "style_text": "warm minimal",
                                         "budget_total_usd": 1200}).json()["plan_id"]
    _wait(client, pid, "done")
    assert seen["budget_total_usd"] == 1200 and seen["budget_usd"] is None


SOFA = "ikea-glostad-sofa-knisa-dark-gray-40595942"
TABLE = "ikea-borgeby-coffee-table-birch-veneer-27-1-2-70389356"


def _live(monkeypatch, prices):
    """prices: product_id -> live price, an Exception instance to raise, or missing for the catalog price."""
    by_url = {p["source_url"]: p for p in srv._products().values()}
    seen = []

    def fake(url, cat):
        p = by_url[url]
        seen.append((p["id"], cat))
        v = prices.get(p["id"], p["price_usd"])
        if isinstance(v, Exception):
            raise v
        return {"price_usd": v}
    monkeypatch.setattr(srv, "_fetch_live", fake)
    return seen


def _price_recs(plan):
    return [a for a in plan["audit"] if a.get("decision") == "live price re-checked"]


def test_live_check_same_price_approves_all_same(client, monkeypatch):
    seen = _live(monkeypatch, {})
    pid, cat = _plan_with_cart([SOFA, TABLE])
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 200
    appr = r.json()["cart"]["approval"]
    assert appr["approved"] is True and appr["live_check"] == "all_same" and appr["checked_at"].endswith("Z")
    assert sorted(seen) == sorted([(SOFA, "sofa"), (TABLE, "coffee_table")])
    recs = _price_recs(r.json())
    assert [x["product_id"] for x in recs] == [SOFA, TABLE] and {x["status"] for x in recs} == {"price_same"}
    rec = recs[0]
    assert rec["step"] == "cart" and rec["source"] == {"kind": "catalog", "url": cat[SOFA]["source_url"]}
    assert rec["input"]["catalog_price_usd"] == rec["input"]["live_price_usd"] == cat[SOFA]["price_usd"]
    assert "same as the catalog" in rec["why"]
    # idempotent: approving the same cart again does not re-fetch
    client.post(f"/api/plan/{pid}/approve")
    assert len(seen) == 2


def test_live_check_changed_price_holds_then_reapproves(client, monkeypatch):
    pid, cat = _plan_with_cart([SOFA, TABLE])
    new = round(cat[SOFA]["price_usd"] + 50, 2)
    _live(monkeypatch, {SOFA: new})
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["error"].startswith("prices changed") and len(d["changes"]) == 1
    ch = d["changes"][0]
    assert ch["product_id"] == SOFA and ch["status"] == "price_changed" and ch["live_price_usd"] == new
    p = store.get(pid)
    assert "approval" not in p["cart"]
    assert p["cart"]["total_usd"] == round(new + cat[TABLE]["price_usd"], 2)
    assert next(c for c in p["cart"]["items"] if c["product_id"] == SOFA)["price_usd"] == new
    assert {x["product_id"]: x["status"] for x in _price_recs(p)} == {SOFA: "price_changed", TABLE: "price_same"}
    # IKEA's price is stable now, so the second approve passes
    r2 = client.post(f"/api/plan/{pid}/approve")
    assert r2.status_code == 200
    appr = r2.json()["cart"]["approval"]
    assert appr["live_check"] == "all_same" and appr["total_usd"] == round(new + cat[TABLE]["price_usd"], 2)
    assert len(_price_recs(r2.json())) == 4


def test_live_check_unavailable_holds(client, monkeypatch):
    import urllib.error
    pid, _ = _plan_with_cart([SOFA, TABLE])
    _live(monkeypatch, {SOFA: urllib.error.HTTPError("u", 410, "Gone", {}, None),
                        TABLE: urllib.error.HTTPError("u", 404, "Not Found", {}, None)})
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 409
    d = r.json()["detail"]
    assert {c["status"] for c in d["changes"]} == {"unavailable"} and "must be swapped" in d["error"]
    p = store.get(pid)
    assert "approval" not in p["cart"] and {x["status"] for x in _price_recs(p)} == {"unavailable"}
    assert all("Swap this item" in x["why"] for x in _price_recs(p))


def test_live_check_page_without_price_does_not_block(client, monkeypatch):
    """A page that loads with no price is check_failed (not 'unavailable'), so approval is not stuck behind a 409."""
    pid, cat = _plan_with_cart([SOFA, TABLE])
    _live(monkeypatch, {SOFA: None})
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 200
    appr = r.json()["cart"]["approval"]
    assert appr["approved"] is True and appr["live_check"] == "partial"
    recs = {x["product_id"]: x for x in _price_recs(r.json())}
    assert recs[SOFA]["status"] == "check_failed" and "listed no price" in recs[SOFA]["why"]
    assert "no longer offers" not in recs[SOFA]["why"]
    assert next(c for c in r.json()["cart"]["items"] if c["product_id"] == SOFA)["price_usd"] == cat[SOFA]["price_usd"]


def test_live_check_unpriced_catalog_item_can_be_approved(client, monkeypatch):
    """A catalog item with price_usd null (e.g. SLATORP) whose IKEA page still lists no price must not block approve."""
    pid, cat = _plan_with_cart([SOFA, TABLE])

    def null_price(plan):
        for c in plan["cart"]["items"]:
            if c["product_id"] == SOFA:
                c["price_usd"] = None
    store.update(pid, null_price)
    _live(monkeypatch, {SOFA: None})
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 200, r.text
    rec = next(x for x in _price_recs(r.json()) if x["product_id"] == SOFA)
    assert rec["status"] == "check_failed" and "catalog had none either" in rec["why"]


def test_live_check_failure_does_not_block(client, monkeypatch):
    pid, _ = _plan_with_cart([SOFA, TABLE])
    _live(monkeypatch, {SOFA: OSError("network down")})
    r = client.post(f"/api/plan/{pid}/approve")
    assert r.status_code == 200
    assert r.json()["cart"]["approval"]["live_check"] == "partial"
    recs = {x["product_id"]: x for x in _price_recs(r.json())}
    assert recs[SOFA]["status"] == "check_failed" and "network down" in recs[SOFA]["why"]
    assert recs[SOFA]["input"]["live_price_usd"] is None and recs[TABLE]["status"] == "price_same"

def test_bag_check_passes_when_items_and_money_match(client):
    real = "ikea-glostad-sofa-knisa-dark-gray-40595942"
    pid, cat = _plan_with_cart([real])
    price = cat[real]["price_usd"]
    bag = {"lines": [{"itemNo": cat[real]["article_number"], "name": "GLOSTAD", "qty": 1, "lineTotal": price}],
           "productsTotal": price}
    r = client.post(f"/api/plan/{pid}/bag", json=bag)
    assert r.status_code == 200
    p = r.json()
    assert p["cart"]["bag"]["verdict"] == "PASS" and p["cart"]["bag"]["bag_total_usd"] == price
    assert p["cart"]["no_purchase"] is True
    rec = [a for a in p["audit"] if a.get("status") == "bag_pass"]
    assert len(rec) == 1 and rec[0]["step"] == "cart" and rec[0]["source"]["kind"] == "browser"
    assert "Nothing is bought" in rec[0]["why"]


def test_bag_check_fails_on_a_price_difference_and_an_extra_item(client):
    real = "ikea-glostad-sofa-knisa-dark-gray-40595942"
    pid, cat = _plan_with_cart([real])
    price = cat[real]["price_usd"]
    bag = {"lines": [{"itemNo": cat[real]["article_number"], "qty": 1, "lineTotal": price + 14},
                     {"itemNo": "704.378.14", "qty": 1, "lineTotal": 9.99}],
           "productsTotal": price + 14 + 9.99}
    p = client.post(f"/api/plan/{pid}/bag", json=bag).json()
    assert p["cart"]["bag"]["verdict"] == "FAIL"
    assert any(d.get("unexpected") for d in p["cart"]["bag"]["item_diff"])
    assert p["cart"]["bag"]["price_deltas"][0]["delta_usd"] == 14
    assert [a["status"] for a in p["audit"] if a["step"] == "cart"][-1] == "bag_fail"
    assert client.post("/api/plan/nope/bag", json=bag).status_code == 404
