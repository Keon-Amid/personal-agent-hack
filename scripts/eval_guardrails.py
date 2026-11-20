"""Guardrail eval: prove with a real run that the agent's tools block bad picks and allow good ones.

No LLM. It calls the SAME functions the agent's MCP tools call (agent.tools.*, agent.senso.check, fit.claims), on
fresh plans in a temp plan store, with exact room numbers, and records what actually happened in each scenario:

  1. too_wide_wall            wall 88 in: fit_options rates every sofa wider than 88 in no_fit (wall math); the pick fits
  2. door_too_small           door 24 x 80 in: a product with a box whose smallest side is over 24 in is no_fit
  3. over_budget              per-item $200: pick never returns a pricier sofa; cart_add refuses one over budget
  4. senso_catches_wrong_fact the real claim text verifies; the same text with a wrong width gets a Senso conflict
  5. cart_refuses_unverified  cart_add with no Senso check is refused (ok False) and audited
  6. good_pick_passes         fitting, in-budget pick + real Senso check + cart_add -> in the cart

Live calls: Superlinked (1 text style call + 1 rerank per plan, 4 plans) and Senso (fact checks, no credits).
The Senso cache is pointed at a fresh temp dir so every check in this run is a live call (or a hit on a call made
earlier in this same run, flagged "cached": true).
Writes contracts/eval.json and prints a table. Run from the repo root:
    .venv/bin/python scripts/eval_guardrails.py
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "contracts" / "eval.json"
STYLE = "warm minimal, light oak"
SENSO_Q = "Does the {name} match its catalog specs and the Room Furnisher rules?"  # same question as tools.senso_check


def load_dotenv(path: Path = REPO / ".env") -> None:
    """Same rule as server/app.py: put .env keys into os.environ (existing variables win). Never printed."""
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


# ---------------------------------------------------------------- helpers

def _tools():
    from agent import tools
    return tools


def _new_plan(exact: dict) -> str:
    from agent import store
    pid = store.new_plan()["plan_id"]
    out = _tools().analyze_room(pid, style_text=STYLE, exact=exact)
    if not out["ok"]:
        raise RuntimeError(f"analyze_room failed: {out.get('error')}")
    return pid


def _audit(pid: str, **match) -> list[dict]:
    recs = _tools().get_plan(pid)["audit"]
    return [r for r in recs if all(r.get(k) == v for k, v in match.items())]


def _check(results: list[dict], name: str) -> list[dict]:
    return [r for r in results if r["check"] == name]


def _short(item: dict | None) -> dict | None:
    if not item:
        return None
    return {"product_id": item["product_id"], "name": item["name"], "price_usd": item["price_usd"],
            "width_in": item["dims_in"]["w"], "fit_verdict": item["fit"]["verdict"],
            "fit_math": [r["math"] for r in item["fit"]["results"]]}


def _senso_summary(res: dict | None) -> dict | None:
    if not res:
        return None
    return {"check_id": res.get("check_id"), "accuracy_pct": res.get("accuracy_pct"), "cached": res.get("cached"),
            "verdicts": [c.get("verdict") for c in res.get("claims") or []],
            "conflicts": [{"claim": c.get("claim"), "quote": c.get("quote")}
                          for c in res.get("claims") or [] if c.get("verdict") == "conflict"]}


def _usd(v) -> str:
    """Price for the 'happened' text; catalog prices can be null (e.g. SLATORP)."""
    return "no price" if v is None else f"${v:g}"


def _tally(res: dict) -> str:
    vs = [c.get("verdict") for c in res.get("claims") or []]
    return ", ".join(f"{vs.count(v)} {v}" for v in dict.fromkeys(vs)) or "no claims"


# ---------------------------------------------------------------- scenarios

def too_wide_wall(ctx: dict) -> dict:
    t = _tools()
    pid = _new_plan({"wall": 88, "depth": 150, "door_width": 36, "door_height": 80})
    ctx["wall_plan"] = pid
    opts = t.fit_options(pid, "sofa")["options"]
    wide = [o for o in opts if t._product(o["product_id"])["dims_in"]["w"] > 88]
    wide_ok = [o for o in wide if o["fit"] != "fits" and any(r["verdict"] == "no_fit" for r in _check(o["fit_results"], "wall"))]
    res = t.pick(pid, "sofa")
    item = res.get("picked")
    ctx["wall_item"] = item
    wide_ids = {o["product_id"] for o in wide}
    picked_ok = bool(item) and item["fit"]["verdict"] == "fits" and item["dims_in"]["w"] <= 88 \
        and item["product_id"] not in wide_ids
    passed = bool(wide) and len(wide_ok) == len(wide) and picked_ok
    rejected_recs = [r for r in _audit(pid, step="pick", decision="rejected") if r.get("product_id") in wide_ids]
    return {
        "kind": "block", "blocked": len(wide_ok), "allowed": 1 if picked_ok else 0, "passed": passed,
        "counts": f"blocked = sofas wider than 88 in that fit_options rated no_fit on the wall check ({len(wide_ok)} of "
                  f"{len(wide)}); allowed = the sofa pick returned",
        "happened": f"{len(wide_ok)}/{len(wide)} sofas wider than 88 in rated no_fit by the wall check; picked "
                    + (f'{item["name"]} ({item["dims_in"]["w"]:g} in, fit {item["fit"]["verdict"]})' if item else "nothing"),
        "evidence": {
            "plan_id": pid,
            "wide_sofas": [{"product_id": o["product_id"], "fit": o["fit"],
                            "wall_math": [r["math"] for r in _check(o["fit_results"], "wall")]} for o in wide],
            "pick_audit_rejected": [{"product_id": r["product_id"], "status": r.get("status"), "why": r["why"]}
                                    for r in rejected_recs],
            "picked": _short(item),
        },
    }


def door_too_small(ctx: dict) -> dict:
    t = _tools()
    slot = "armchair"
    cands = [p for p in t._products() if p["category"] == slot and p.get("packages_in")
             and any(min(b["w"], b["d"], b["h"]) > 24 for b in p["packages_in"])]
    if not cands:
        return {"kind": "block", "blocked": 0, "allowed": 0, "passed": False,
                "happened": "no armchair in the catalog has a box over 24 in on its smallest side", "evidence": {}}
    target = cands[0]
    pid = _new_plan({"wall": 120, "depth": 150, "door_width": 24, "door_height": 80})
    opts = {o["product_id"]: o for o in t.fit_options(pid, slot)["options"]}
    o = opts[target["id"]]
    door_bad = [r for r in _check(o["fit_results"], "doorway_width") if r["verdict"] == "no_fit"]
    res = t.pick(pid, slot)
    item = res.get("picked")
    ctx["door_plan"] = pid
    picked_ok = item is None or (item["product_id"] != target["id"] and all(
        r["verdict"] == "fits" for r in item["fit"]["results"] if r["check"].startswith("doorway")))
    blocked_by_door = [p for p, x in opts.items()
                       if any(r["verdict"] == "no_fit" for r in _check(x["fit_results"], "doorway_width"))]
    passed = o["fit"] == "no_fit" and bool(door_bad) and picked_ok
    return {
        "kind": "block", "blocked": len(blocked_by_door), "allowed": 1 if item and picked_ok else 0, "passed": passed,
        "counts": f"blocked = armchairs fit_options rated no_fit on the doorway ({len(blocked_by_door)} of {len(opts)}); "
                  "allowed = the armchair pick returned",
        "happened": f'{target["name"]} is {o["fit"]} (box smallest side over 24 in); {len(blocked_by_door)}/{len(opts)} '
                    f'armchairs blocked by the 24 in door; picked '
                    + (f'{item["name"]}' if item else "nothing"),
        "evidence": {
            "plan_id": pid, "product_id": target["id"], "packages_in": target["packages_in"], "fit": o["fit"],
            "doorway_math": [r["math"] for r in door_bad],
            "picked": _short(item),
            "picked_doorway_math": [r["math"] for r in (item["fit"]["results"] if item else [])
                                    if r["check"].startswith("doorway")],
        },
    }


def over_budget(ctx: dict) -> dict:
    t = _tools()
    pid = _new_plan({"wall": 120, "depth": 150, "door_width": 36, "door_height": 80})
    t.set_budget(pid, per_item_usd=200)
    a = t.pick(pid, "sofa")
    a_item = a.get("picked")
    over_rejects = [r for r in a.get("rejected", []) if r["why"].startswith("over budget")]
    pick_ok = (a_item is not None and a_item["price_usd"] <= 200) or \
        (a_item is None and "$200" in (a.get("error") or ""))

    # Part B: get an over-$200 sofa into the slot (no budget), Senso-check it, then set the budget and try the cart.
    t.set_budget(pid)  # clear
    b = t.pick(pid, "sofa")
    item = b.get("picked")
    swaps = 0
    while item and (item["price_usd"] is None or item["price_usd"] <= 200) and swaps < 10:  # skip unpriced too
        item = t.swap(pid, "sofa").get("picked") or None
        swaps += 1
    cart = sens = None
    cart_ok = False
    if item and item["price_usd"] is not None and item["price_usd"] > 200:
        sens = t.senso_check(pid, "sofa")
        t.set_budget(pid, per_item_usd=200)
        cart = t.cart_add(pid, "sofa", "eval: should be refused, over the per-item budget")
        cart_ok = cart["ok"] is False and "per-item budget" in (cart.get("error") or "")
    refusal = _audit(pid, step="cart", decision="refused")
    passed = pick_ok and cart_ok
    note = "" if sens is None or sens["ok"] else " (note: its Senso check also failed)"
    return {
        "kind": "block", "blocked": len(over_rejects) + (1 if cart_ok else 0), "allowed": 1 if a_item and pick_ok else 0,
        "passed": passed,
        "counts": f"blocked = sofas pick skipped as over budget ({len(over_rejects)}) + cart_add refusals "
                  f"({1 if cart_ok else 0}); allowed = the under-budget sofa pick returned",
        "happened": (f'pick under $200 returned {a_item["name"]} {_usd(a_item["price_usd"])}' if a_item else
                     f'pick returned none: {a.get("error")}') + f"; skipped {len(over_rejects)} pricier sofas; "
                    + (f'cart_add of {item["name"]} {_usd(item["price_usd"])} -> ok={cart["ok"]}{note}' if cart else
                       "could not get an over-$200 sofa into the slot to test cart_add"),
        "evidence": {
            "plan_id": pid, "pick_budget_cap": {"usd": a.get("budget_cap_usd"), "why": a.get("budget_cap_why")},
            "pick_picked": _short(a_item), "pick_over_budget_rejected": over_rejects,
            "cart_item": _short(item), "cart_item_senso": _senso_summary((sens or {}).get("senso")),
            "cart_result": {"ok": cart["ok"], "error": cart.get("error")} if cart else None,
            "cart_refusal_audit": refusal[-1:] if refusal else [],
        },
    }


def senso_catches_wrong_fact(ctx: dict) -> dict:
    import importlib
    from fit.claims import claim_text
    senso = importlib.import_module("agent.senso")  # same lookup as agent.tools._senso
    t = _tools()
    item = ctx.get("wall_item")
    if not item:
        return {"kind": "block", "blocked": 0, "allowed": 0, "passed": False,
                "happened": "no picked sofa from too_wide_wall to build a claim from", "evidence": {}}
    p = t._product(item["product_id"])
    results = item["fit"]["results"]
    good = claim_text(p, results)
    w = p["dims_in"]["w"]
    wrong_w = w + 12
    bad = good.replace(f"as {w:g} inches wide", f"as {wrong_w:g} inches wide")
    if bad == good:
        return {"kind": "block", "blocked": 0, "allowed": 0, "passed": False,
                "happened": "could not find the width sentence in the claim text", "evidence": {"text": good}}
    q = SENSO_Q.format(name=p["name"])
    g = senso.check(good, q)
    b = senso.check(bad, q)
    g_ok = senso.verdict_ok(g)
    b_all = [c for c in b.get("claims") or [] if c.get("verdict") == "conflict"]
    # Only a conflict on the width sentence we changed counts; a spurious conflict elsewhere is not "caught".
    b_conf = [c for c in b_all if f"{wrong_w:g}" in (c.get("claim") or "")]
    passed = g_ok and bool(b_conf)
    return {
        "kind": "block", "blocked": 1 if b_conf else 0, "allowed": 0, "passed": passed,
        "counts": "blocked = Senso conflicts on the changed width claim; the correct-text check is a precondition, "
                  "not counted as an allowed pick",
        "happened": f'correct text: {_tally(g)}, acc {g.get("accuracy_pct")}%; '
                    f'same text with width {w:g} -> {wrong_w:g} in: {_tally(b)}, acc {b.get("accuracy_pct")}%, '
                    f'{len(b_conf)} conflict(s) on the {wrong_w:g} in width claim',
        "evidence": {"product_id": p["id"], "true_width_in": w, "wrong_width_in": wrong_w,
                     "correct_text": good, "corrupted_text": bad,
                     "correct_check": _senso_summary(g), "corrupted_check": _senso_summary(b)},
    }


def cart_refuses_unverified(ctx: dict) -> dict:
    t = _tools()
    pid = ctx.get("door_plan")
    item = t.get_plan(pid)["items"][0] if pid and t.get_plan(pid)["items"] else None
    slot = item["slot"] if item else None
    if not item:  # door plan picked nothing: fall back to the wall plan's sofa (no senso_check run on it yet)
        pid, slot = ctx["wall_plan"], "sofa"
        item = t.get_plan(pid)["items"][0]
    assert not item.get("senso"), "precondition: no Senso check on this slot"
    res = t.cart_add(pid, slot, "eval: should be refused, no Senso check")
    rec = _audit(pid, step="cart", decision="refused")
    plan = t.get_plan(pid)
    in_cart = any(c["product_id"] == item["product_id"] for c in plan["cart"]["items"])
    passed = res["ok"] is False and bool(rec) and not in_cart
    return {
        "kind": "block", "blocked": 1 if passed else 0, "allowed": 0, "passed": passed,
        "counts": "blocked = cart_add refusals for a slot with no Senso check",
        "happened": f'cart_add {item["name"]} with no Senso check -> ok={res["ok"]}: {res.get("error")}',
        "evidence": {"plan_id": pid, "slot": slot, "result": {"ok": res["ok"], "error": res.get("error")},
                     "refusal_audit": rec[-1:], "in_cart": in_cart},
    }


def good_pick_passes(ctx: dict) -> dict:
    t = _tools()
    pid = _new_plan({"wall": 88, "depth": 150, "door_width": 36, "door_height": 80})
    t.set_budget(pid, total_usd=1500, per_item_usd=1000)
    res = t.pick(pid, "sofa")
    item = res.get("picked")
    if not item:
        return {"kind": "allow", "blocked": 0, "allowed": 0, "passed": False,
                "happened": f'pick returned nothing: {res.get("error")}', "evidence": {"plan_id": pid}}
    sens = t.senso_check(pid, "sofa")
    cart = t.cart_add(pid, "sofa", "eval: fits the 88 in wall, within budget, Senso verified")
    plan = t.get_plan(pid)
    in_cart = any(c["product_id"] == item["product_id"] for c in plan["cart"]["items"])
    priced_ok = item["price_usd"] is not None and item["price_usd"] <= 1000
    passed = item["fit"]["verdict"] == "fits" and priced_ok and sens["ok"] and cart["ok"] and in_cart
    return {
        "kind": "allow", "blocked": 0, "allowed": 1 if passed else 0, "passed": passed,
        "counts": "allowed = the fitting, in-budget, Senso-verified sofa that reached the cart",
        "happened": f'{item["name"]} {_usd(item["price_usd"])} fit {item["fit"]["verdict"]}; senso ok={sens["ok"]}; '
                    f'cart_add ok={cart["ok"]}; in cart={in_cart}',
        "evidence": {"plan_id": pid, "picked": _short(item), "senso": _senso_summary(sens.get("senso")),
                     "cart_result": {"ok": cart["ok"], "error": cart.get("error")},
                     "cart": plan["cart"], "cart_audit": _audit(pid, step="cart")[-1:],
                     "senso_audit": _audit(pid, step="senso_check")[-1:]},
    }


SCENARIOS = [
    ("too_wide_wall", "wall 88 in: fit_options rates every sofa wider than 88 in no_fit, with the wall math; the "
                      "picked sofa fits",
     too_wide_wall),
    ("door_too_small", "door 24 x 80 in: an armchair with a box whose smallest side is over 24 in is rejected for "
                       "the doorway, with the math", door_too_small),
    ("over_budget", "per-item budget $200: pick never returns a sofa over $200; cart_add refuses a sofa over $200",
     over_budget),
    ("senso_catches_wrong_fact", "Senso verifies the real claim text and flags a conflict when the width is wrong",
     senso_catches_wrong_fact),
    ("cart_refuses_unverified", "cart_add on a slot with no Senso check is refused (ok False) and audited",
     cart_refuses_unverified),
    ("good_pick_passes", "a fitting, in-budget pick with a real Senso check is added to the cart", good_pick_passes),
]


def run(out: Path | None = OUT) -> dict:
    ctx: dict = {}
    scenarios = []
    with tempfile.TemporaryDirectory() as plans, tempfile.TemporaryDirectory() as cache:
        old = {k: os.environ.get(k) for k in ("ROOM_FURNISHER_PLANS_DIR", "ROOM_FURNISHER_SENSO_CACHE")}
        os.environ["ROOM_FURNISHER_PLANS_DIR"], os.environ["ROOM_FURNISHER_SENSO_CACHE"] = plans, cache
        try:
            for name, should, fn in SCENARIOS:
                t0 = time.time()
                try:
                    r = fn(ctx)
                except Exception as e:  # report it; never turn an error into a pass
                    r = {"kind": "?", "blocked": 0, "allowed": 0, "passed": False, "counts": "",
                         "happened": f"error: {type(e).__name__}: {e}", "evidence": {}}
                scenarios.append({"name": name, "should": should, "happened": r["happened"], "pass": r["passed"],
                                  "kind": r["kind"], "blocked": r["blocked"], "allowed": r["allowed"],
                                  "counts": r.get("counts", ""),
                                  "seconds": round(time.time() - t0, 1), "evidence": r["evidence"]})
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                             text=True).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                               text=True).stdout.strip()
        if sha and dirty:
            sha += "-dirty"  # uncommitted changes: HEAD alone cannot reproduce this run
    except OSError:
        sha = None
    result = {
        "ran_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": sha,
        "how": "scripts/eval_guardrails.py: agent.tools + agent.senso called directly (no LLM), fresh temp plans, "
               "exact room numbers, live Superlinked + Senso",
        "scenarios": scenarios,
        "summary": {"passed": sum(s["pass"] for s in scenarios), "total": len(scenarios),
                    "no_fit_or_refused_events": sum(s["blocked"] for s in scenarios),
                    "allowed_events": sum(s["allowed"] for s in scenarios),
                    "note": "Headline is passed/total. The two event totals add different kinds of events (no_fit "
                            "product ratings, budget skips, cart refusals, Senso conflicts; picks returned); each "
                            "scenario's 'counts' says what its numbers count. Only good_pick_passes is an allow "
                            "scenario."},
    }
    if out is not None:
        out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result


def table(result: dict) -> str:
    rows = [f'{"scenario":<26} {"pass":<5} {"blk":>3} {"ok":>3}  what happened']
    for s in result["scenarios"]:
        rows.append(f'{s["name"]:<26} {"PASS" if s["pass"] else "FAIL":<5} {s["blocked"]:>3} {s["allowed"]:>3}  '
                    f'{s["happened"]}')
    m = result["summary"]
    rows.append(f'passed {m["passed"]}/{m["total"]} · no_fit/refused events {m["no_fit_or_refused_events"]} · '
                f'allowed events {m["allowed_events"]} · git {result["git_sha"]} · {result["ran_at"]}')
    return "\n".join(rows)


if __name__ == "__main__":
    load_dotenv()
    res = run()
    print(table(res))
    print(f"wrote {OUT.relative_to(REPO)}")
    sys.exit(0 if res["summary"]["passed"] == res["summary"]["total"] else 1)
