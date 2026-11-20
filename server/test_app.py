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

    def fake_run_agent(room_input, photo_b64=None, style_text=None, budget_usd=None, on_event=None, plan_id=None):
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
                        lambda room, photo_b64=None, style_text=None, budget_usd=None, plan_id=None:
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
