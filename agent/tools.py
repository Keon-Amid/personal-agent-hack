"""The agent's tools: the contract shared by the FastAPI path (agent.agent) and the MCP server (agent.mcp_server).

The tools enforce the rules; the model only chooses the order and explains.
- pick only returns items that fit (fit.pick walks the Superlinked style ranking and skips no_fit/unsure).
- cart_add refuses any item whose Senso check has a conflict or no verified claim.
- every tool appends its own AuditRecord to the plan (agent.store), so a model can't skip a check or invent a fit.

Every tool takes plain JSON values and returns a JSON-serializable dict that includes plan_id and plan_url.
On a rule violation a tool returns {"ok": False, "error": ..., plan_id, plan_url} (and audits the refusal)
rather than raising, so the model can read why and recover. Unknown plan_id / slot raises ValueError.

Claims are checked by agent.senso (A3); room photos are measured by agent.room (A4).
"""
from __future__ import annotations

import base64
import binascii
import importlib
import json
import os
from functools import lru_cache
from pathlib import Path

from . import store
from .types import audit

SLOT_ENUM = ["sofa", "armchair", "coffee_table", "rug", "floor_lamp"]
ROOM_KEYS = ("wall", "depth", "door_width", "door_height")
REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- helpers

@lru_cache(maxsize=1)
def _catalog() -> tuple[dict, ...]:
    return tuple(json.loads((REPO / "data" / "products.json").read_text())["products"])


def _products() -> list[dict]:
    return list(_catalog())


def _product(pid: str) -> dict:
    return next(p for p in _catalog() if p["id"] == pid)


@lru_cache(maxsize=1)
def _emb() -> dict:
    return json.loads((REPO / "data" / "style_embeddings.json").read_text())


def _sie():
    return importlib.import_module("data.sie")


def _senso():
    return importlib.import_module("agent.senso")  # looked up at call time so tests can swap the module


def _room_estimator():
    return importlib.import_module("agent.room")


def _load(plan_id: str) -> dict:
    try:
        return store.get(plan_id)
    except KeyError:
        raise ValueError(f"unknown plan_id {plan_id!r}") from None


def _check_slot(slot: str) -> None:
    if slot not in SLOT_ENUM:
        raise ValueError(f"unknown slot {slot!r}; use one of {SLOT_ENUM}")


def _ids(plan: dict) -> dict:
    return {"plan_id": plan["plan_id"], "plan_url": plan["plan_url"]}


def _commit(plan_id: str, records: list[dict], mutate=None) -> dict:
    """Locked read-modify-write: apply `mutate` to the fresh plan, append the audit records (ts stamped)."""
    def fn(plan: dict) -> None:
        if mutate:
            mutate(plan)
        plan.setdefault("audit", []).extend(records)
    return store.update(plan_id, fn)


def _refuse(plan: dict, step: str, error: str, slot: str | None = None, **extra) -> dict:
    """Audit a refusal and return the error dict the model reads."""
    rec = audit(step, decision="refused", status="refused", why=error, **({"item_slot": slot} if slot else {}))
    _commit(plan["plan_id"], [rec])
    return {**_ids(plan), "ok": False, "error": error, **extra}


def _budget(plan: dict) -> dict:
    b = plan.get("budget") or {}
    return {"total_usd": b.get("total_usd"), "per_item_usd": b.get("per_item_usd")}


def _spent_elsewhere(plan: dict, slot: str, picked: bool = False) -> float:
    """What the other slots cost: their picked items (picked=True, for pick/swap) or the cart (for cart_add).
    This slot's own item is left out, since a swap or re-pick replaces it."""
    mine = (_slot_item(plan, slot) or {}).get("product_id")
    if picked:
        return round(sum((i.get("price_usd") or 0) for i in plan["items"] if i["slot"] != slot), 2)
    return round(sum((c.get("price_usd") or 0) for c in plan["cart"]["items"] if c["product_id"] != mine), 2)


def _cap(plan: dict, slot: str, asked: float | None) -> tuple[float | None, str]:
    """The most this slot's item may cost: the smallest of what the model asked for, the person's per-item
    budget, and what's left of the person's total budget. The tools enforce this; the prompt can't loosen it."""
    b = _budget(plan)
    limits = []
    if asked is not None:
        limits.append((float(asked), f"asked ${float(asked):g}"))
    if b["per_item_usd"] is not None:
        limits.append((b["per_item_usd"], f'per-item budget ${b["per_item_usd"]:g}'))
    if b["total_usd"] is not None:
        left = round(b["total_usd"] - _spent_elsewhere(plan, slot, picked=True), 2)
        limits.append((max(left, 0.0), f'${left:g} left of the ${b["total_usd"]:g} total'))
    if not limits:
        return None, "no budget"
    cap, why = min(limits, key=lambda t: t[0])
    return cap, why


def _call_sie(fn, *args, **kw):
    """data.sie raises SystemExit when SIE_API_KEY is missing; turn every failure into a readable error."""
    try:
        return fn(*args, **kw), None
    except SystemExit as e:
        return None, f"Superlinked unavailable: {e}"
    except Exception as e:  # network / API errors: report them, never fake a ranking
        return None, f"Superlinked call failed: {type(e).__name__}: {e}"


def _room_complete(room: dict | None) -> bool:
    return bool(room) and all(room.get(k) for k in ROOM_KEYS)


def _detected(det) -> str | None:
    if not det:
        return None
    first = det[0]
    return first.get("style") if isinstance(first, dict) else str(first)


def _style_names(ps) -> list[str]:
    return [s["style"] if isinstance(s, dict) else str(s) for s in (ps or [])]


def _rejected(rows: list[dict]) -> list[dict]:
    return [{"product_id": r["id"], "name": r["name"], "status": r["status"], "why": r["why"]} for r in rows]


def _cart_total(cart: dict) -> None:
    cart["total_usd"] = round(sum(c["price_usd"] or 0 for c in cart["items"]), 2)


def _drop_from_cart(plan: dict, product_id: str | None) -> None:
    if product_id is None:
        return
    cart = plan["cart"]
    cart["items"] = [c for c in cart["items"] if c["product_id"] != product_id]
    _cart_total(cart)


def _slot_item(plan: dict, slot: str) -> dict | None:
    return next((i for i in plan.get("items", []) if i["slot"] == slot), None)


def _options(plan: dict, slot: str) -> list[dict]:
    from fit.options import options, room
    r = plan["room"]
    return options(_products(), slot, room(*(r[k] for k in ROOM_KEYS)))


def _style_for(plan: dict, slot: str) -> tuple[dict | None, list[dict], str | None]:
    """Cached style_match for the slot, or run it (one Superlinked rerank call). Returns (style, records, error)."""
    cached = plan.get("state", {}).get("style", {}).get(slot)
    if cached:
        return cached, [], None
    R = plan.get("state", {}).get("room_analysis")
    if not R:
        return None, [], "no room style yet: call analyze_room with a photo or style words first"
    res, err = _call_sie(_sie().style_match, _products(), slot, _emb(), room=R)
    if err:
        return None, [], err
    top = res["ranked"][0] if res["ranked"] else None
    rec = audit("rank", item_slot=slot, input=res["style_text"], source=dict(res["source"]),
                decision="ranked by style",
                why=f'{len(res["ranked"])} {slot} products ranked against "{res["style_text"]}"'
                    + (f'; #1 {top["name"]}' if top else ""))
    return res, [rec], None


def _item(slot: str, chosen: dict, rejected: list[dict]) -> dict:
    p = _product(chosen["id"])
    s = chosen["style"]
    return {
        "slot": slot, "product_id": p["id"], "name": p["name"], "price_usd": p["price_usd"],
        "dims_in": p["dims_in"], "image_url": p.get("image_url"), "source_url": p["source_url"],
        "style": {"rank": s["style_rank"], "fused": s.get("style_fused"), "photo_score": s.get("photo_score"),
                  "text_score": s.get("text_score"), "product_styles": _style_names(s.get("product_styles"))},
        "fit": {"verdict": chosen["fit"], "results": chosen["fit_results"]},
        "senso": None,
        "why": f'{chosen["style_why"]}; fits; ${chosen["price_usd"]:g}',
        "why_source": {"kind": "template"},
        "rejected": _rejected(rejected),
    }


def _run_pick(plan_id: str, slot: str, budget_usd: float | None, swapping: bool) -> dict:
    from fit.checks import FITS
    from fit.pick import pick as fit_pick
    plan = _load(plan_id)
    step = "swap" if swapping else "pick"
    if not _room_complete(plan.get("room")):
        return _refuse(plan, step, "room measurements missing: call analyze_room first", slot)
    state = plan.get("state", {})
    shown = list(state.get("shown", {}).get(slot, []))
    if swapping:
        if not state.get("style", {}).get(slot) or not shown:
            return _refuse(plan, step, f"nothing picked for {slot} yet: call pick first", slot)
        budget_usd = state.get("budget", {}).get(slot)
    cap, cap_why = _cap(plan, slot, budget_usd)
    style, records, err = _style_for(plan, slot)
    if err:
        return _refuse(plan, step, err, slot)
    opts = _options(plan, slot)
    res = fit_pick(opts, style, budget_usd=cap, exclude=shown if swapping else [])
    chosen = res["picked"]
    if chosen is not None and chosen["fit"] != FITS:  # belt and braces: the tool never hands out a non-fit
        chosen = None
    records += [audit(r.pop("step"), **r) for r in (dict(x) for x in res["audit"])]
    old = _slot_item(plan, slot)
    old_id = old["product_id"] if old else None
    item = _item(slot, chosen, res["rejected"]) if chosen else None

    if swapping:
        if item is None:
            records.append(audit("swap", item_slot=slot, product_id=old_id, source={"kind": "fit"},
                                 decision="no swap", status="none_left",
                                 why=f'no other {slot} fits and matches; kept {old["name"] if old else "nothing"}; '
                                     f'excluded {len(shown)} shown'))
        else:
            records.append(audit("swap", item_slot=slot, product_id=item["product_id"], source={"kind": "fit"},
                                 decision="swapped", status="fits", input={"excluded": shown},
                                 why=f'swapped {old["name"] if old else "nothing"} for {item["name"]}; '
                                     f'{len(shown)} earlier picks excluded'))

    def mutate(p: dict) -> None:
        st = p.setdefault("state", {})
        st.setdefault("style", {})[slot] = style
        if not swapping:
            st.setdefault("budget", {})[slot] = budget_usd
        if item is None:
            if not swapping:  # a fresh pick that finds nothing clears the slot
                p["items"] = [i for i in p["items"] if i["slot"] != slot]
                _drop_from_cart(p, old_id)
            return
        sh = st.setdefault("shown", {}).setdefault(slot, [])
        if item["product_id"] not in sh:
            sh.append(item["product_id"])
        p["items"] = [i for i in p["items"] if i["slot"] != slot] + [item]
        _drop_from_cart(p, old_id)

    plan = _commit(plan_id, records, mutate)
    out = {**_ids(plan), "ok": item is not None, "slot": slot, "picked": item, "rejected": _rejected(res["rejected"])}
    if item is None:
        out["error"] = (f"no other {slot} fits the room and matches the style" if swapping
                        else f"no {slot} fits the room" + (f" within ${cap:g} ({cap_why})" if cap is not None else ""))
    if cap is not None:
        out["budget_cap_usd"], out["budget_cap_why"] = cap, cap_why
    if swapping:
        out["excluded"] = shown
    return out


# ---------------------------------------------------------------- tools


def analyze_room(plan_id: str, photo_b64: str | None = None, style_text: str | None = None,
                 exact: dict | None = None, scan_path: str | None = None, scan_wall: str | None = None) -> dict:
    """Set the room's measurements and style on the plan.

    photo_b64: base64 room photo; used for Superlinked room-style detection (data.sie.analyze_room) and, when
        no exact numbers are given, for estimated measurements (source "estimated:door"/"estimated:paper",
        with error_in > 0, so wide items may come back "unsure").
    style_text: the person's words for the style ("warm minimal, light oak"); used if no photo, or fused with it.
    exact: measurements the person typed, in inches: {"wall", "depth", "door_width", "door_height"};
        stored as fit.measurement(v, 0, "user"). Exact values override estimates key by key.
    The Superlinked room vector is stored in plan["state"] so later style_match calls make no new room call.
    Audits step "estimate_room" (source photo/template) and the style detection (source superlinked).
    Returns {plan_id, plan_url, room, style}.
    """
    from fit import measurement
    plan = _load(plan_id)
    exact = {k: v for k, v in (exact or {}).items() if v is not None}
    bad = [k for k in exact if k not in ROOM_KEYS]
    if bad:
        return _refuse(plan, "estimate_room", f"unknown measurement keys {bad}; use {list(ROOM_KEYS)}")
    photo = None
    if photo_b64:
        try:
            photo = base64.b64decode(photo_b64.split(",", 1)[-1] if photo_b64.startswith("data:") else photo_b64,
                                     validate=False)
        except (binascii.Error, ValueError) as e:
            return _refuse(plan, "estimate_room", f"photo_b64 is not valid base64: {e}")

    room = dict(plan.get("room") or {})
    records: list[dict] = []
    if scan_path and len(exact) < len(ROOM_KEYS):
        # LiDAR scan (GLB/OBJ/PLY on this machine): measures wall (longest, or scan_wall), depth and any open door.
        # Precedence per key: exact > scan > photo; agent.room.estimate applies it and writes the audit records.
        try:
            est_mod = _room_estimator()
            if est_mod.is_roomplan(scan_path):  # named walls/doors: alistair's fit.scan (gives the real door)
                est, est_records = est_mod.estimate_roomplan(scan_path, scan_wall, exact)
            else:  # raw LiDAR mesh: agent.room_scan
                with open(scan_path, "rb") as fh:
                    est, est_records = est_mod.estimate(photo, exact, scan_bytes=fh.read(),
                                                        scan_name=os.path.basename(scan_path), scan_wall=scan_wall)
        except Exception as e:
            return _refuse(plan, "estimate_room", f"room scan failed: {type(e).__name__}: {e}")
        room.update({k: est[k] for k in ROOM_KEYS if isinstance(est.get(k), dict)})
        records.extend(est_records)
        exact = {}
    if photo is not None and len(exact) < len(ROOM_KEYS) and not scan_path:
        # agent.room.estimate(photo, exact) -> (room, [AuditRecord]); exact values (source user) override the
        # photo estimate key by key, and it writes its own estimate_room records.
        try:
            est, est_records = _room_estimator().estimate(photo, exact)
        except Exception as e:
            records.append(audit("estimate_room", input={"photo": True}, source={"kind": "photo"},
                                 decision="estimate failed", status="error",
                                 why=f"room estimate failed: {type(e).__name__}: {e}"))
        else:
            room.update({k: est[k] for k in ROOM_KEYS if isinstance(est.get(k), dict)})
            records.extend(est_records)
            exact = {}  # already applied by estimate()
    if exact:
        try:
            for k, v in exact.items():
                room[k] = measurement(float(v), 0, "user")
        except (TypeError, ValueError) as e:
            return _refuse(plan, "estimate_room", f"bad measurement: {e}")
        records.append(audit("estimate_room", input=exact, source={"kind": "template", "measured_by": "user"},
                             decision="measurements set",
                             why="The person typed exact measurements (source user, error 0): "
                                 + ", ".join(f"{k} {v:g} in" for k, v in exact.items())))

    R = None
    if photo is not None or style_text:
        R, err = _call_sie(_sie().analyze_room, room_photo=photo, style_text=style_text)
        if err:
            records.append(audit("estimate_room", source={"kind": "superlinked"}, decision="style detection failed",
                                 status="error", why=err))
        else:
            det = _detected(R.get("detected_style"))
            records.append(audit(
                "estimate_room", input={"photo": photo is not None, "style_text": style_text},
                source={"kind": "superlinked", "detected": R.get("detected_style")},
                decision=f'style: {R["style_text"]}',
                why=(f"detected from the room photo: {det}" if det else "from the person's words")))
    style = {"style_text": R["style_text"], "detected_style": _detected(R.get("detected_style"))} if R else None

    def mutate(p: dict) -> None:
        old = {k: (p.get("room") or {}).get(k) for k in ROOM_KEYS}
        p["room"] = {**room, "photo_url": room.get("photo_url")} if room else None
        st = p.setdefault("state", {})
        if any(old[k] and old[k] != (room or {}).get(k) for k in ROOM_KEYS):
            # the room changed: earlier picks and cart may no longer fit, so start the furnishing over
            p["items"], st["shown"] = [], {}
            p["cart"] = {**(p.get("cart") or {}), "items": [], "total_usd": 0.0}
        if R is not None:
            p["style"] = style
            st["room_analysis"] = R
            st["style"] = {}  # new room style: rankings must be redone

    plan = _commit(plan_id, records, mutate)
    out = {**_ids(plan), "ok": True, "room": plan["room"], "style": plan["style"]}
    missing = [k for k in ROOM_KEYS if not (plan["room"] or {}).get(k)]
    if missing:
        out["ok"] = False
        out["error"] = f"still missing measurements: {missing}; ask the person or send a photo"
    if not plan["style"]:
        out["ok"] = False
        out["error"] = (out.get("error", "") + "; " if "error" in out else "") + \
            "no style yet: give style words or a photo" + \
            (f" ({records[-1]['why']})" if records and records[-1].get("status") == "error" else "")
    return out


def style_match(plan_id: str, slot: str) -> dict:
    """Rank the catalog products for one slot by style against the room (data.sie.style_match).

    Uses the room analysis stored by analyze_room; caches the result in plan["state"]["style"][slot].
    Audits step "rank" (source superlinked).
    Returns {plan_id, plan_url, slot, style_text, detected_style, ranked: [{product_id, name, style_rank,
    photo_rank, photo_score, text_rank, text_score, product_styles}]}.
    """
    _check_slot(slot)
    plan = _load(plan_id)
    plan.setdefault("state", {}).setdefault("style", {}).pop(slot, None)  # explicit call: rank fresh
    res, records, err = _style_for(plan, slot)
    if err:
        return _refuse(plan, "rank", err, slot)
    plan = _commit(plan_id, records, lambda p: p.setdefault("state", {}).setdefault("style", {}).__setitem__(slot, res))
    return {**_ids(plan), "ok": True, "slot": slot, "style_text": res["style_text"],
            "detected_style": _detected(res.get("detected_style")),
            "ranked": [{"product_id": r["id"], "name": r["name"], "style_rank": r["style_rank"],
                        "photo_rank": r["photo_rank"], "photo_score": r["photo_score"],
                        "text_rank": r["text_rank"], "text_score": r["text_score"],
                        "product_styles": _style_names(r.get("product_styles"))} for r in res["ranked"]]}


def fit_options(plan_id: str, slot: str) -> dict:
    """Fit every catalog product for one slot against the plan's room (fit.options.options).

    Audits step "rank" (source fit) with counts of fits/unsure/no_fit.
    Returns {plan_id, plan_url, slot, options: [{product_id, name, price_usd, rating, review_count,
    fit, fit_results (each with its math), best_value, why}]}.
    """
    _check_slot(slot)
    plan = _load(plan_id)
    if not _room_complete(plan.get("room")):
        return _refuse(plan, "rank", "room measurements missing: call analyze_room first", slot)
    opts = _options(plan, slot)
    counts = {v: sum(o["fit"] == v for o in opts) for v in ("fits", "unsure", "no_fit")}
    rec = audit("rank", item_slot=slot, source={"kind": "fit"}, decision="fit checked",
                input={k: plan["room"][k] for k in ROOM_KEYS},
                why=f'{len(opts)} {slot} products: {counts["fits"]} fit, {counts["unsure"]} unsure, '
                    f'{counts["no_fit"]} no_fit; best value: '
                    + (", ".join(o["name"] for o in opts if o["best_value"]) or "none"))
    plan = _commit(plan_id, [rec])
    return {**_ids(plan), "ok": True, "slot": slot, "counts": counts,
            "options": [{"product_id": o["id"], "name": o["name"], "price_usd": o["price_usd"],
                         "rating": o["rating"], "review_count": o["review_count"], "fit": o["fit"],
                         "fit_results": o["fit_results"], "best_value": o["best_value"], "why": o["why"]}
                        for o in opts]}


def pick(plan_id: str, slot: str, budget_usd: float | None = None) -> dict:
    """Pick the best style match that fits (and is within budget) for one slot (fit.pick.pick).

    Runs style_match / fit_options first if they haven't run for this slot. Writes the Item to plan["items"]
    (replacing any earlier pick for the slot) with why_source template until the agent explains in cart_add.
    Appends fit.pick's audit records (ts stamped). Never returns an item whose fit is not "fits".
    Returns {plan_id, plan_url, slot, picked: Item | None, rejected: [{product_id, name, status, why}]}.
    picked is None (with the reasons in rejected) when nothing fits.
    """
    _check_slot(slot)
    return _run_pick(plan_id, slot, budget_usd, swapping=False)


def senso_check(plan_id: str, slot: str) -> dict:
    """Fact-check the picked item for one slot against the Senso knowledge base.

    Builds the claim text from the item's catalog facts (name, price, dims) and the clearance rule it relies
    on (walkway, wall fit, doorway boxes, rug margin), posts it to Senso /org/evals/text, and stores
    item["senso"] = {check_id, accuracy_pct, claims: [{claim, verdict, quote}]}.
    Only "conflict" blocks the item; "unsupported" on room numbers is expected (fit/ decides fit).
    Audits step "senso_check" (source senso, check_id).
    Returns {plan_id, plan_url, slot, product_id, senso, ok: no conflict and >= 1 verified}.
    """
    _check_slot(slot)
    plan = _load(plan_id)
    item = _slot_item(plan, slot)
    if item is None:
        return _refuse(plan, "senso_check", f"nothing picked for {slot}: call pick first", slot)
    try:
        sn = _senso()
        from fit.claims import claim_text  # alistair's wording: the phrasing Senso actually scores (CONTRACT.md)
        text = claim_text(_product(item["product_id"]), (item.get("fit") or {}).get("results") or [])
        res = sn.check(text, f'Does the {item["name"]} match its catalog specs and the Room Furnisher rules?')
    except Exception as e:  # never fake a check: report the failure
        return _refuse(plan, "senso_check", f"Senso check failed: {type(e).__name__}: {e}", slot,
                       product_id=item["product_id"])
    ok = _senso_ok(res)
    verdicts = [c["verdict"] for c in res.get("claims", [])]
    tally = ", ".join(f"{verdicts.count(v)} {v}" for v in ("verified", "conflict", "unsupported", "not_verifiable")
                      if v in verdicts)
    conflicts = [c["claim"] for c in res.get("claims", []) if c["verdict"] == "conflict"]
    rec = audit("senso_check", item_slot=slot, product_id=item["product_id"], input=text,
                source={"kind": "senso", "check_id": res.get("check_id")},
                decision="passed" if ok else "blocked", status="verified" if ok else "conflict" if conflicts
                else "not_verified",
                why=f'{tally or "no claims"}; accuracy {res.get("accuracy_pct")}%'
                    + (f'; conflict: {"; ".join(conflicts)}' if conflicts else ""))
    pid = item["product_id"]

    def mutate(p: dict) -> None:
        it = _slot_item(p, slot)
        if it and it["product_id"] == pid:  # a swap in between invalidates this check
            it["senso"] = {k: res.get(k) for k in ("check_id", "accuracy_pct", "claims")}  # contract fields only

    plan = _commit(plan_id, [rec], mutate)
    return {**_ids(plan), "ok": ok, "slot": slot, "product_id": pid, "senso": res}


def _senso_ok(res: dict | None) -> bool:
    """The cart gate: A3's verdict_ok AND our own floor (no conflict, at least one verified claim)."""
    if not res or not res.get("claims"):
        return False
    verdicts = [c.get("verdict") for c in res["claims"]]
    if "conflict" in verdicts or "verified" not in verdicts:
        return False
    return bool(_senso().verdict_ok(res))


def swap(plan_id: str, slot: str) -> dict:
    """Replace the slot's pick with the next fitting style match, excluding every product picked before.

    Uses the cached style_match (no new Superlinked call) and fit.pick.pick(exclude=...). Clears the slot's
    Senso check and removes it from the cart. Audits step "swap".
    Returns the same shape as pick, plus {"excluded": [product_id, ...]}.
    """
    _check_slot(slot)
    return _run_pick(plan_id, slot, None, swapping=True)


def cart_add(plan_id: str, slot: str, why: str) -> dict:
    """Add the slot's picked item to the cart (a cart, never a purchase: cart.no_purchase is always true).

    REFUSES (ok False, audited) unless the item's Senso check exists, has no "conflict" claim and has at
    least one "verified" claim. why = the agent's explanation for the person; stored on the item with
    why_source {"kind": "claude"} and in the audit record (step "cart", source claude).
    Returns {plan_id, plan_url, ok, slot, cart} or {plan_id, plan_url, ok: False, error}.
    """
    _check_slot(slot)
    plan = _load(plan_id)
    item = _slot_item(plan, slot)
    if item is None:
        return _refuse(plan, "cart", f"nothing picked for {slot}: call pick first", slot)
    if not item.get("senso"):
        return _refuse(plan, "cart", f"{item['name']} has no Senso check: call senso_check first", slot,
                       product_id=item["product_id"])
    try:
        ok = _senso_ok(item["senso"])
    except Exception as e:
        return _refuse(plan, "cart", f"could not evaluate the Senso check: {type(e).__name__}: {e}", slot)
    if not ok:
        return _refuse(plan, "cart", f"{item['name']} failed its Senso check (a conflict, or no verified claim); "
                                     "swap it or check again", slot, product_id=item["product_id"])
    b = _budget(plan)
    price = item.get("price_usd")
    if (b["per_item_usd"] is not None or b["total_usd"] is not None) and price is None:
        return _refuse(plan, "cart", f"{item['name']} has no price on the IKEA page, so the budget can't be "
                                     "checked: swap it", slot, product_id=item["product_id"])
    if b["per_item_usd"] is not None and price > b["per_item_usd"]:
        return _refuse(plan, "cart", f"{item['name']} costs ${price:g}, over the per-item budget of "
                                     f"${b['per_item_usd']:g}: swap it", slot, product_id=item["product_id"])
    if b["total_usd"] is not None:
        spent = _spent_elsewhere(plan, slot)
        if spent + price > b["total_usd"] + 1e-9:
            return _refuse(plan, "cart", f"{item['name']} (${price:g}) would bring the cart to "
                                         f"${spent + price:g}, over the ${b['total_usd']:g} total budget: swap it "
                                         f"or pick with budget_usd <= {max(b['total_usd'] - spent, 0):g}",
                           slot, product_id=item["product_id"])
    why = (why or "").strip()
    pid = item["product_id"]
    rec = audit("cart", item_slot=slot, product_id=pid, source={"kind": "claude" if why else "template"},
                decision="added to cart", status="in_cart", why=why or "(the agent gave no explanation)")

    def mutate(p: dict) -> None:
        it = _slot_item(p, slot)
        if not it or it["product_id"] != pid:
            return
        it["why"], it["why_source"] = why or it["why"], {"kind": "claude"} if why else it["why_source"]
        cart = p["cart"]
        cart["items"] = [c for c in cart["items"] if c["product_id"] != pid] + [
            {"product_id": pid, "name": it["name"], "price_usd": it["price_usd"], "source_url": it["source_url"]}]
        cart["no_purchase"] = True
        _cart_total(cart)

    plan = _commit(plan_id, [rec], mutate)
    return {**_ids(plan), "ok": True, "slot": slot, "cart": plan["cart"]}


def set_budget(plan_id: str, total_usd: float | None = None, per_item_usd: float | None = None) -> dict:
    """Store the person's budget on the plan. From then on pick/swap never return a pricier item and cart_add
    refuses anything over the per-item limit or that would take the cart past the total. Both None = no budget.
    Audits step "agent", decision "budget set". Returns {plan_id, plan_url, ok, budget, spent_usd}."""
    plan = _load(plan_id)
    for name, v in (("total_usd", total_usd), ("per_item_usd", per_item_usd)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            return _refuse(plan, "agent", f"{name} must be a positive number of dollars, got {v!r}")
    budget = {"total_usd": float(total_usd) if total_usd is not None else None,
              "per_item_usd": float(per_item_usd) if per_item_usd is not None else None}
    parts = ([f'total ${budget["total_usd"]:g}'] if budget["total_usd"] is not None else []) + \
            ([f'${budget["per_item_usd"]:g} per item'] if budget["per_item_usd"] is not None else [])
    spent = plan["cart"].get("total_usd", 0.0)
    rec = audit("agent", source={"kind": "template", "set_by": "person"},
                decision="budget set" if parts else "budget cleared",
                input=budget, status="set",
                why=("The person's budget: " + ", ".join(parts) + "; enforced by pick, swap and cart_add")
                if parts else "No budget.")

    def mutate(p: dict) -> None:
        p["budget"] = budget if parts else None

    plan = _commit(plan_id, [rec], mutate)
    warn = {}
    if budget["total_usd"] is not None and spent > budget["total_usd"]:
        warn["warning"] = f"the cart already totals ${spent:g}, over the new ${budget['total_usd']:g}: swap items"
    return {**_ids(plan), "ok": True, "budget": plan.get("budget"), "spent_usd": spent, **warn}


def get_plan(plan_id: str) -> dict:
    """Return the whole plan (room, style, items, cart, audit) without plan["state"]. Not audited."""
    plan = _load(plan_id)
    plan.pop("state", None)
    return plan


_PLAN = {"plan_id": {"type": "string", "description": "The plan to work on."}}
_SLOT = {"slot": {"type": "string", "enum": SLOT_ENUM, "description": "Which piece of furniture."}}


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOL_SPECS: list[dict] = [
    {"name": "analyze_room",
     "description": "Set the room's measurements and style. Give a room photo (base64) and/or style words, and "
                    "exact measurements in inches if the person has them. Returns the room and detected style.",
     "input_schema": _schema({
         **_PLAN,
         "photo_b64": {"type": ["string", "null"], "description": "Base64 room photo."},
         "style_text": {"type": ["string", "null"], "description": "The person's style words."},
         "exact": {"type": ["object", "null"], "description": "Exact inches the person measured.",
                   "properties": {k: {"type": "number"} for k in ("wall", "depth", "door_width", "door_height")},
                   "additionalProperties": False},
         "scan_path": {"type": ["string", "null"], "description": "Path to a LiDAR room scan (GLB/OBJ/PLY) on this machine."},
         "scan_wall": {"type": ["string", "null"], "description": "Scan wall id the furniture goes against (default: longest)."},
     }, ["plan_id"])},
    {"name": "style_match",
     "description": "Rank the products for one slot by how well they match the room's style (Superlinked).",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "fit_options",
     "description": "Check every product for one slot against the room: wall, walkway, doorway. Shows the math "
                    "and which are best value.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "pick",
     "description": "Pick the best style match that fits the room (and budget) for one slot. Only fitting items "
                    "can be picked; the others come back with the reason they were rejected.",
     "input_schema": _schema({**_PLAN, **_SLOT,
                              "budget_usd": {"type": ["number", "null"], "description": "Max price for this item."}},
                             ["plan_id", "slot"])},
    {"name": "senso_check",
     "description": "Fact-check the picked item's specs, price and clearance rules against the Senso knowledge "
                    "base. Required before cart_add.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "swap",
     "description": "Replace the slot's pick with the next fitting style match, never repeating an earlier pick.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "cart_add",
     "description": "Add the slot's picked item to the cart (no purchase is made). Refused unless its Senso check "
                    "has a verified claim and no conflict. 'why' is your one- or two-sentence explanation for the "
                    "person.",
     "input_schema": _schema({**_PLAN, **_SLOT, "why": {"type": "string"}}, ["plan_id", "slot", "why"])},
    {"name": "set_budget",
     "description": "Set the person's budget as soon as they mention one: total_usd for the whole room and/or "
                    "per_item_usd for each piece. The tools then enforce it: pick and swap never return a pricier "
                    "item and cart_add refuses anything that breaks it.",
     "input_schema": _schema({**_PLAN,
                              "total_usd": {"type": ["number", "null"], "description": "Budget for the whole room."},
                              "per_item_usd": {"type": ["number", "null"], "description": "Max price per item."}},
                             ["plan_id"])},
    {"name": "get_plan",
     "description": "Get the whole plan: room, style, items, cart and audit trail.",
     "input_schema": _schema({**_PLAN}, ["plan_id"])},
]
