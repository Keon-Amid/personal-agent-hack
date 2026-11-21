"""HTTP API for the web app: start a furnishing run, watch it grow, swap a pick, take the quiz.

    .venv/bin/uvicorn server.app:app --port 8000          # from the repo root

A thin layer over agent/: no new decisions are made here. Every plan change still goes through agent.tools,
so the fit and Senso rules (and their audit records) apply exactly as in an agent run.

POST /api/plan            {room, style_text?, budget_usd? (per item), budget_total_usd? (whole room), photo_b64?, quiz_answers?} -> {plan_id} at once
GET  /api/plan/{id}       the Plan (contracts/plan.live.json shape) + "run": {status, error}; poll it
POST /api/plan/{id}/swap  {slot} -> swap, Senso check, cart_add; returns the Plan
POST /api/plan/{id}/approve  re-checks each cart item's live IKEA price, then the person approves the cart (no purchase);
                          returns the Plan + shopping_list, or 409 with the price changes if IKEA's price moved
GET  /api/quiz            agent/quiz.json
POST /api/quiz/score      {answers} -> agent.quiz.score + catalog_support
GET  /api/health          which live services are configured (never prints a key)
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

REPO = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = REPO / ".env") -> None:
    """Put .env keys into os.environ (existing variables win). Values are never logged."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #")[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


load_dotenv()

from agent import agent as agent_mod  # noqa: E402  (after .env, so the agent's child process sees the keys)
from agent import bag_reconcile, quiz, store, tools  # noqa: E402
from agent.types import ALLOWED_SLOTS, DELIVERY_NOTE, audit, now_ts  # noqa: E402
from data import fetch_ikea  # noqa: E402

app = FastAPI(title="Room Furnisher API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ROOM_FURNISHER_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

# Run status per plan, for this server process. The plan itself lives in agent.store (shared with the agent).
RUNS: dict[str, dict] = {}
_RUNS_LOCK = threading.Lock()
MAX_RUNNING = 2  # each run is a Claude Code process; keep the laptop responsive during the demo


class Room(BaseModel):
    wall: float | None = None
    depth: float | None = None
    door_width: float | None = None
    door_height: float | None = None


class PlanRequest(BaseModel):
    room: Room = Room()
    style_text: str | None = None
    budget_usd: float | None = None
    budget_total_usd: float | None = None
    photo_b64: str | None = None
    quiz_answers: dict[str, str] | None = None
    scan_path: str | None = None  # LiDAR scan on this machine, e.g. assets/room_scan_roomplan.glb (RoomPlan or raw mesh)
    scan_wall: str | None = None  # scan wall id the furniture goes against (default: longest)


class SwapRequest(BaseModel):
    slot: str


class BagLine(BaseModel):
    itemNo: str
    name: str | None = None
    qty: int = 1
    lineTotal: float | str | None = None


class BagRequest(BaseModel):
    """readBag() from scripts/ikea_bag.js, run by the browser agent on ikea.com/us/en/shoppingcart/."""
    lines: list[BagLine] = []
    productsTotal: float | str | None = None


class QuizRequest(BaseModel):
    answers: dict[str, str]


def _set_run(pid: str, **kw) -> None:
    with _RUNS_LOCK:
        RUNS.setdefault(pid, {}).update(kw)


def _run(pid: str, req: PlanRequest, style_text: str | None, budget: float | None) -> None:
    try:
        agent_mod.run_agent(req.room.model_dump(exclude_none=True), photo_b64=req.photo_b64,
                            style_text=style_text, budget_usd=budget, budget_total_usd=req.budget_total_usd,
                            plan_id=pid, scan_path=req.scan_path, scan_wall=req.scan_wall)
        _set_run(pid, status="done", finished_at=time.time())
    except Exception as e:  # AgentError, AgentTimeout, or a bug: the browser must see it, not a silent hang
        _set_run(pid, status="error", error=f"{type(e).__name__}: {e}", finished_at=time.time())


def _running() -> int:
    with _RUNS_LOCK:
        return sum(1 for r in RUNS.values() if r.get("status") == "running")


@app.post("/api/plan")
def start_plan(req: PlanRequest) -> dict:
    if not any(req.room.model_dump(exclude_none=True).values()) and not req.photo_b64 and not req.scan_path:
        raise HTTPException(400, "send room measurements (inches), a room photo or a scan_path")
    if _running() >= MAX_RUNNING:
        raise HTTPException(429, f"{MAX_RUNNING} runs are already going; wait for one to finish")
    style_text, budget, persona = req.style_text, req.budget_usd, None
    if req.quiz_answers:
        try:
            persona = quiz.score(req.quiz_answers)
        except ValueError as e:
            raise HTTPException(400, f"quiz: {e}")
        style_text = style_text or persona["style_text"]
        budget = budget if budget is not None else persona["budget_usd"]
    pid = uuid.uuid4().hex[:12]
    _set_run(pid, status="running", error=None, started_at=time.time(), style_text=style_text,
             budget_usd=budget, persona=persona)
    threading.Thread(target=_run, args=(pid, req, style_text, budget), daemon=True).start()
    return {"plan_id": pid, "plan_url": store.plan_url(pid)}


def _empty(pid: str) -> dict:
    """What GET returns in the moment before the agent has written the plan file."""
    return {"plan_id": pid, "plan_url": store.plan_url(pid), "room": None, "style": None, "items": [],
            "cart": {"items": [], "total_usd": 0.0, "delivery_note": DELIVERY_NOTE, "no_purchase": True},
            "audit": []}


def _status_from_audit(plan: dict) -> dict:
    """Run status for a plan this server process did not start (e.g. after a restart), read from its audit trail.

    run_agent always ends with one "agent" record: status done ("agent finished"), timeout ("stopped: timeout") or
    error ("agent failed"). If the last agent record is none of those, the run was cut off (or is still going in an
    orphaned child), so it is "interrupted", never "done". A plan with no agent records was not made by run_agent
    (tests, or tools called directly), so there is no run to wait for: "done".
    """
    recs = [a for a in plan.get("audit") or [] if a.get("step") == "agent"]
    if not recs:
        return {"status": "done", "error": None}
    last = recs[-1]
    if last.get("status") == "done":
        return {"status": "done", "error": None}
    if last.get("status") == "timeout" or (last.get("status") == "error" and last.get("decision") == "agent failed"):
        return {"status": "error", "error": f"{last.get('decision')}: {last.get('why')}"}
    return {"status": "interrupted",
            "error": "server restarted mid-run: the agent never finished this plan; start a new plan"}


def _run_status(pid: str, plan: dict | None) -> dict:
    with _RUNS_LOCK:
        run = dict(RUNS.get(pid) or {})
    if run:
        return {"status": run.get("status", "running"), "error": run.get("error"), "persona": run.get("persona")}
    return {**(_status_from_audit(plan) if plan else {"status": "unknown", "error": None}), "persona": None}


def _require_finished(pid: str, action: str) -> dict:
    """404 if the plan is unknown; 409 unless its run is done or error. Returns the plan."""
    try:
        plan = tools.get_plan(pid)
    except (KeyError, ValueError):
        with _RUNS_LOCK:
            known = pid in RUNS
        if known:
            raise HTTPException(409, f"the agent is still working on this plan; {action} when it finishes")
        raise HTTPException(404, f"no plan {pid}")
    run = _run_status(pid, plan)
    if run["status"] == "running":
        raise HTTPException(409, f"the agent is still working on this plan; {action} when it finishes")
    if run["status"] not in ("done", "error"):
        raise HTTPException(409, f"this plan's run is {run['status']} ({run['error']}); {action} is blocked")
    return plan


@app.get("/api/plan/{pid}")
def get_plan(pid: str) -> dict:
    try:
        plan = tools.get_plan(pid)
    except (KeyError, ValueError):
        with _RUNS_LOCK:
            known = pid in RUNS
        if not known:
            raise HTTPException(404, f"no plan {pid}")
        plan = _empty(pid)
    plan["run"] = _run_status(pid, plan)
    return plan


_SWAP_CART_WHY = "Added after the person's swap; it passed its Senso check."


@app.post("/api/plan/{pid}/swap")
def swap(pid: str, req: SwapRequest) -> dict:
    if req.slot not in ALLOWED_SLOTS:
        raise HTTPException(400, f"slot must be one of {list(ALLOWED_SLOTS)}")
    _require_finished(pid, "swap")

    def requested(plan: dict) -> None:
        # The person is the actor here, not the agent: say so before tools.swap writes its own records.
        plan.setdefault("audit", []).append(
            audit("swap", item_slot=req.slot, source={"kind": "template", "requested_by": "person"},
                  decision="swap requested by the person", status="requested",
                  why="The person clicked swap on screen."))

    def withdraw(plan: dict) -> None:
        # Only a swap that replaced the item changes the cart; then the earlier approval no longer matches it.
        appr = plan["cart"].pop("approval", None)
        if appr and appr.get("approved"):
            plan["audit"].append(audit("cart", item_slot=req.slot, source={"kind": "template"},
                                       decision="approval withdrawn: cart changed by swap", status="approval_withdrawn",
                                       why="The person swapped an item after approving, so the earlier approval no "
                                           "longer matches the cart. Approve again to confirm the new cart.",
                                       input={"previous_approval": appr}))

    store.update(pid, requested)
    steps = {"swap": tools.swap(pid, req.slot)}
    picked = steps["swap"].get("picked")
    if picked:
        store.update(pid, withdraw)
        steps["senso_check"] = tools.senso_check(pid, req.slot)
        # No why text: this swap was the person's click, not the agent's reasoning, so cart_add records it
        # with source "template" instead of claiming a Claude explanation.
        steps["cart_add"] = tools.cart_add(pid, req.slot, "")
        if steps["cart_add"].get("ok"):
            _relabel_swap_cart_record(pid, req.slot)
    plan = get_plan(pid)
    plan["swap_result"] = {k: {kk: v.get(kk) for kk in ("ok", "error", "picked") if kk in v}
                           for k, v in steps.items()}
    return plan


def _relabel_swap_cart_record(pid: str, slot: str) -> None:
    """cart_add("") writes why "(the agent gave no explanation)"; on the person's swap that wrongly credits the
    agent, so name the person's swap instead (source stays "template")."""
    def fix(plan: dict) -> None:
        for rec in reversed(plan.get("audit") or []):
            if rec.get("step") == "cart" and rec.get("item_slot") == slot and rec.get("status") == "in_cart":
                if rec.get("source", {}).get("kind") == "template":
                    rec["why"] = _SWAP_CART_WHY
                    rec["source"] = {"kind": "template", "requested_by": "person"}
                return
    store.update(pid, fix)


_PRODUCTS: dict[str, dict] | None = None


def _products() -> dict[str, dict]:
    """data/products.json by product id, loaded once."""
    global _PRODUCTS
    if _PRODUCTS is None:
        data = json.loads((REPO / "data" / "products.json").read_text())
        _PRODUCTS = {p["id"]: p for p in data.get("products", [])}
    return _PRODUCTS


# Live re-check of IKEA's price before approval. Tests replace _fetch_live; the real one re-reads the product page.
_fetch_live = fetch_ikea.product
LIVE_CHECK_TIMEOUT_S = 20.0
_BLOCKING = ("price_changed", "unavailable")


def _usd(v) -> str:
    return "no price" if v is None else f"${v:,.2f}"


def _check_one(c: dict, plan_item: dict) -> dict:
    """Re-read one cart item's IKEA page. Never raises: failures become status check_failed."""
    pid = c["product_id"]
    url = c.get("source_url")
    category = plan_item.get("category") or (_products().get(pid) or {}).get("category") or plan_item.get("slot")
    res = {"product_id": pid, "item_slot": plan_item.get("slot"), "name": c.get("name"), "url": url,
           "catalog_price_usd": c.get("price_usd"), "live_price_usd": None, "error": None}
    if not url:
        res.update(status="check_failed", error="the cart item has no IKEA page")
    else:
        try:
            live = _fetch_live(url, category)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                res.update(status="unavailable", error=f"IKEA's page returned HTTP {e.code}")
            else:
                res.update(status="check_failed", error=f"IKEA's page returned HTTP {e.code}")
        except Exception as e:  # network error, timeout, page layout change
            res.update(status="check_failed", error=f"{type(e).__name__}: {e}"[:200])
        else:
            lp = live.get("price_usd") if isinstance(live, dict) else None
            res["live_price_usd"] = lp
            if lp is None:
                # A page that loaded but shows no price is a layout quirk or a regional page as often as a dropped
                # item, and the catalog may never have had a price: don't claim "unavailable" or block approval.
                had = "the catalog had none either" if res["catalog_price_usd"] is None else "the catalog price was kept"
                res.update(status="check_failed", error=f"IKEA's page listed no price; {had}")
            elif res["catalog_price_usd"] is not None and round(lp, 2) == round(res["catalog_price_usd"], 2):
                res["status"] = "price_same"
            else:
                res["status"] = "price_changed"
    res["checked_at"] = now_ts()
    return res


def _live_check(cart_items: list[dict], plan_items: list[dict]) -> list[dict]:
    """Re-check every cart item concurrently, with one overall deadline. One result per cart item, in cart order."""
    by_pid = {i.get("product_id"): i for i in plan_items}
    pool = ThreadPoolExecutor(max_workers=min(8, max(1, len(cart_items))))
    futures = [pool.submit(_check_one, c, by_pid.get(c["product_id"]) or {}) for c in cart_items]
    deadline = time.monotonic() + LIVE_CHECK_TIMEOUT_S
    out = []
    for c, f in zip(cart_items, futures):
        try:
            out.append(f.result(timeout=max(0.0, deadline - time.monotonic())))
        except FutureTimeout:
            slot = (by_pid.get(c["product_id"]) or {}).get("slot")
            out.append({"product_id": c["product_id"], "item_slot": slot, "name": c.get("name"),
                        "url": c.get("source_url"), "catalog_price_usd": c.get("price_usd"), "live_price_usd": None,
                        "status": "check_failed", "error": f"timed out after {LIVE_CHECK_TIMEOUT_S:.0f} s",
                        "checked_at": now_ts()})
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def _live_why(r: dict) -> str:
    cat, live, st = r["catalog_price_usd"], r["live_price_usd"], r["status"]
    if st == "price_same":
        return f"IKEA's page still lists {_usd(live)}, same as the catalog."
    if st == "price_changed":
        return (f"IKEA's page now lists {_usd(live)}; the catalog had {_usd(cat)}. The cart now uses the live price, "
                "so approval was held until the person approves again.")
    if st == "unavailable":
        return (f"IKEA's product page is gone ({r['error']}), so approval was held. Swap this item to approve.")
    if cat is None:
        return f"The live IKEA check found no price ({r['error']}); approval was not blocked."
    return (f"The live IKEA check failed ({r['error']}), so the catalog price {_usd(cat)} was kept and approval "
            "was not blocked.")


def _live_record(r: dict) -> dict:
    extra = {"item_slot": r["item_slot"]} if r.get("item_slot") else {}
    return audit("cart", **extra, product_id=r["product_id"], source={"kind": "catalog", "url": r["url"]},
                 decision="live price re-checked", status=r["status"], why=_live_why(r),
                 input={"catalog_price_usd": r["catalog_price_usd"], "live_price_usd": r["live_price_usd"],
                        "checked_at": r["checked_at"]})


def _already_approved(cart: dict) -> bool:
    prev = cart.get("approval") or {}
    ids = [c["product_id"] for c in cart.get("items") or []]
    return bool(prev.get("approved") and prev.get("product_ids") == ids
                and prev.get("total_usd") == cart.get("total_usd", 0.0))


@app.post("/api/plan/{pid}/approve")
def approve(pid: str) -> dict:
    snap = _require_finished(pid, "approve")
    cart_items = snap["cart"].get("items") or []
    # Network fetches happen outside the plan lock; skipped when nothing to check or the same cart is approved.
    results = [] if not cart_items or _already_approved(snap["cart"]) else _live_check(cart_items, snap.get("items") or [])
    checked_ids = [r["product_id"] for r in results]
    held: list[dict] = []

    def mutate(plan: dict) -> None:
        # Checked under the plan lock so two clicks cannot both approve (or approve an emptied cart).
        cart = plan["cart"]
        items = cart.get("items") or []
        if _already_approved(cart):
            return  # idempotent: the same cart is already approved; add no second audit record
        if not items:
            raise HTTPException(409, "the cart is empty; nothing to approve")
        ids = [c["product_id"] for c in items]
        if ids != checked_ids:
            raise HTTPException(409, "the cart changed while its prices were being checked; approve again")
        trail = plan.setdefault("audit", [])
        trail.extend(_live_record(r) for r in results)
        for r in results:
            if r["status"] in _BLOCKING:
                held.append({k: r[k] for k in ("product_id", "item_slot", "name", "status", "catalog_price_usd",
                                               "live_price_usd")})
            if r["status"] == "price_changed":
                for c in items:
                    if c["product_id"] == r["product_id"]:
                        c["price_usd"] = r["live_price_usd"]
                for it in plan.get("items") or []:
                    if it.get("product_id") == r["product_id"]:
                        it["price_usd"] = r["live_price_usd"]
        if held:
            tools._cart_total(cart)
            cart.pop("approval", None)  # any earlier approval was for other prices
            return
        total = cart.get("total_usd", 0.0)
        partial = any(r["status"] == "check_failed" for r in results)
        cart["approval"] = {"approved": True, "approved_at": now_ts(), "total_usd": total, "item_count": len(items),
                            "product_ids": ids, "live_check": "partial" if partial else "all_same",
                            "checked_at": max(r["checked_at"] for r in results)}
        cart["no_purchase"] = True
        trail.append(audit(
            "cart", source={"kind": "template"}, decision="cart approved by the person", status="approved",
            why="The person approved the cart on screen. No purchase is made; the shopping list links to each "
                "IKEA product page.",
            input={"total_usd": total, "product_ids": ids}))

    store.update(pid, mutate)
    if held:
        gone = any(h["status"] == "unavailable" for h in held)
        msg = "prices changed since the plan was made; review and approve again"
        if gone:
            msg += "; items whose IKEA page is gone (unavailable) must be swapped first"
        raise HTTPException(409, {"error": msg,
                                  "changes": held})
    plan = get_plan(pid)
    catalog = _products()
    plan["shopping_list"] = [
        {"name": c.get("name"), "article_number": (catalog.get(c["product_id"]) or {}).get("article_number"),
         "price_usd": c.get("price_usd"), "source_url": c.get("source_url")}
        for c in plan["cart"]["items"]]
    plan["action"] = {"kind": "shopping_list", "mocked_checkout": True,
                      "note": "No order is placed. Open each IKEA link to buy."}
    return plan


@app.post("/api/plan/{pid}/bag")
def check_bag(pid: str, req: BagRequest) -> dict:
    """The browser agent filled the person's real IKEA bag and read it back; check it against the cart.

    Items AND money (agent.bag_reconcile): every cart item in the bag once, nothing extra, the bag's total equal
    to the cart's total, and within the plan's whole-room budget if it has one. The result is stored on
    cart.bag and written to the audit trail. Nothing is bought.
    """
    _require_finished(pid, "check the bag")
    catalog = _products()
    bag = req.model_dump()
    out: dict = {}

    def mutate(plan: dict) -> None:
        cart = plan["cart"]
        selection = [{"item_no": (catalog.get(c["product_id"]) or {}).get("article_number") or "", "qty": 1,
                      "price_usd": c.get("price_usd")} for c in cart.get("items") or []]
        if not selection:
            raise HTTPException(409, "the cart is empty; nothing to check the bag against")
        budget = (plan.get("budget") or {}).get("total_usd")
        res = bag_reconcile.reconcile(selection, bag, budget)
        ok = res["verdict"] == "PASS"
        cart["bag"] = {"verdict": res["verdict"], "checked_at": now_ts(), "bag_total_usd": res["bag_total_usd"],
                       "expected_total_usd": res["expected_total_usd"], "item_count": len(bag["lines"]),
                       "item_diff": res["item_diff"], "price_deltas": res["price_deltas"], "reasons": res["reasons"]}
        cart["no_purchase"] = True
        total = res["bag_total_usd"]
        why = (f"{len(selection)} items in the IKEA bag, each at the right quantity; IKEA's total ${total:.2f} "
               f"matches the cart. Nothing is bought until the person pays on IKEA.com." if ok else
               "The IKEA bag does not match the cart: " + "; ".join(res["reasons"]) + ".")
        plan.setdefault("audit", []).append(audit(
            "cart", source={"kind": "browser", "site": "ikea.com", "read_by": "scripts/ikea_bag.js readBag()"},
            decision="IKEA bag filled and checked" if ok else "IKEA bag does not match the cart",
            status="bag_pass" if ok else "bag_fail", why=why,
            input={"bag_total_usd": total, "expected_total_usd": res["expected_total_usd"],
                   "item_diff": res["item_diff"], "price_deltas": res["price_deltas"]}))
        out.update(res)

    store.update(pid, mutate)
    plan = get_plan(pid)
    plan["bag_check"] = out
    return plan


@app.get("/api/quiz")
def get_quiz() -> dict:
    return quiz.QUIZ


@app.post("/api/quiz/score")
def score_quiz(req: QuizRequest) -> dict:
    try:
        r = quiz.score(req.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**r, "catalog_support": quiz.catalog_support(r["style"])}


@app.get("/api/health")
def health() -> dict:
    return {
        "claude_code": bool(shutil.which("claude")),
        "superlinked_key": bool(os.environ.get("SIE_API_KEY")),
        "senso_key": bool(os.environ.get("SENSO_API_KEY")),
        "runs": {"running": _running(), "max": MAX_RUNNING},
    }
