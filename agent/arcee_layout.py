"""Arcee (sponsor) plans where each picked piece goes in a scanned room; fit.layout decides if it is allowed.

Optional and separate: nothing calls this by default, and no existing plan file is changed.

    python3 -m agent.arcee_layout contracts/plan.room_scan.json            # -> contracts/layout.room_scan.json
    python3 -m agent.arcee_layout <plan.json> --scan assets/room_scan_roomplan.glb --model <arcee model id>

How it works:
  1. One Arcee call gets the room (outline, door, existing furniture, all in inches from fit.scan) and the picked
     products with their real sizes, and returns a position and rotation for every piece.
  2. Each proposal is checked with fit.layout.check_layout, the same checks find_spot uses (inside the walls,
     no overlap, door swing clear, spacing, clearance). A piece is accepted only if every item still reads "fits".
  3. Pieces that fail go back to Arcee once, with the failing maths.
  4. Anything still failing is placed by fit.layout.find_spot (deterministic), and marked as such.

So the model proposes and the fit checks decide: a bad proposal is rejected with its maths, never drawn.
Every call is recorded with model, tokens, cost (Arcee's listed prices) and latency. Stdlib only; needs ARCEE_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from fit.checks import FITS
from fit.layout import add_product, check_layout, door_zone, entry_zone, find_spot, layout_from_scan
from fit.scan import load_scan

from . import arcee

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCAN = "assets/room_scan_roomplan.glb"
SYSTEM = (
    "You arrange furniture in a real room. Reply with JSON only, no prose and no code fence: "
    '{"placements":[{"id":"...","x_in":0,"z_in":0,"rotation":0,"why":"at most 12 words"}]}. '
    "All numbers are inches on the floor plane. x_in and z_in are the CENTRE of the piece. "
    "rotation is 0, 90, 180 or 270: at 0 and 180 the piece's width runs along x and its depth along z; "
    "at 90 and 270 they swap. The front faces +z at 0, +x at 90, -z at 180, -x at 270. "
    "Give exactly one placement for every piece in to_place, using its id."
)
RULES = [
    "Every corner of a piece must be inside room_outline.",
    "A piece must not overlap existing furniture or another new piece. Exception: anything may stand on a rug.",
    "Keep every keep_clear zone (the door swing) and every entry_path_keep_clear zone (the way in) empty.",
    "Don't cluster furniture near the door: put the main pieces on the walls farthest from it.",
    "Keep at least 12 in between a new piece and other furniture, and leave 18 in free on some side to reach it.",
    "Sofas, armchairs, lamps and storage go against a wall with their back to it, front facing the room.",
    "Rugs and coffee tables go in the open part of the room; put the coffee table in front of the sofa.",
    # designers' rules of thumb (Apartment Therapy, Homes & Gardens, Houzz living-room clearance guides)
    "Sofa: on the longest wall with no door, facing the room's open centre (or the TV if there is one).",
    "Coffee table: centred on the sofa, 14-18 in from the sofa's front edge.",
    "Armchairs: across from or beside the sofa, angled toward the coffee table, within 7-9 ft of the sofa.",
    "Rug: under the seating group, big enough for at least the front legs of the sofa and chairs.",
    "Floor lamp: beside the sofa's arm or an armchair, or in a corner; never in a walkway.",
    "Walkways: 30-36 in for the main path from the door through the room, 24-30 in behind or between pieces.",
]


def _model() -> str:
    return os.environ.get("ARCEE_LAYOUT_MODEL") or arcee.DEFAULT_MODEL


def room_facts(room: dict) -> dict:
    """What the model is told about the room: only what fit.scan measured."""
    xs = [p[0] for p in room["outline"]]
    zs = [p[1] for p in room["outline"]]
    return {
        "room_outline": room["outline"],
        "x_range": [min(xs), max(xs)], "z_range": [min(zs), max(zs)],
        "doors": [{"id": d["id"], "center": d["center"], "width_in": d["width_in"],
                   "keep_clear": dict(zip(("x0", "z0", "x1", "z1"), [round(v, 1) for v in door_zone(d)])),
                   "entry_path_keep_clear": dict(zip(("x0", "z0", "x1", "z1"), [round(v, 1) for v in entry_zone(d)]))}
                  for d in room.get("doors", [])],
        "existing": [{"id": i["id"], "label": i["label"], "category": i["category"], "x_in": i["x_in"],
                      "z_in": i["z_in"], "w_in": i["w_in"], "d_in": i["d_in"], "rotation": i.get("rotation", 0),
                      "on_floor": i.get("bottom_in", 0) < 24} for i in room["items"]],
    }


def _ask(messages: list[dict], model: str) -> tuple[dict, dict]:
    """One Arcee call -> (parsed JSON, {latency_ms, tokens, cost_usd})."""
    t0 = time.monotonic()
    # Reasoning models think before they answer. Seen live on Nov 20: at 6000 and at 20000 tokens,
    # glm-5.3-flash and deepseek-v4.1-flash spent the whole limit thinking and returned an empty reply
    # (finish_reason "length"). ARCEE_LAYOUT_MAX_TOKENS / ARCEE_LAYOUT_TIMEOUT_S raise the limits.
    max_tokens = int(os.environ.get("ARCEE_LAYOUT_MAX_TOKENS") or 20000)
    out = arcee._http("/chat/completions", {"model": model, "temperature": 0, "max_tokens": max_tokens,
                                            "messages": messages},
                      timeout=int(os.environ.get("ARCEE_LAYOUT_TIMEOUT_S") or 300))
    ms = round((time.monotonic() - t0) * 1000)
    text = (out["choices"][0]["message"].get("content") or "").strip()
    usage = out.get("usage") or {}
    tin, tout = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
    price = arcee.models().get(model, {"in": 0, "out": 0})
    call = {"latency_ms": ms, "input_tokens": tin, "output_tokens": tout,
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
            "finish_reason": out["choices"][0].get("finish_reason"),
            "cost_usd": round(tin * price["in"] + tout * price["out"], 7)}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        parsed = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        parsed = {}
    return parsed, {**call, "reply_chars": len(text), "parsed": bool(parsed.get("placements"))}


def _ask_claude(messages: list[dict], model: str) -> tuple[dict, dict]:
    """The same request answered by the person's local Claude (Claude Code, `claude -p`, signed in). No tools."""
    import subprocess
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    convo = "\n\n".join(f'{m["role"].upper()}: {m["content"]}' for m in messages if m["role"] != "system")
    cmd = ["claude", "-p", convo, "--append-system-prompt", system, "--output-format", "json",
           "--tools", "", "--no-session-persistence"]
    cmd += ["--model", model if model and model != "claude" else os.environ.get("LAYOUT_CLAUDE_MODEL", "sonnet")]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=480, cwd=str(ROOT), stdin=subprocess.DEVNULL)  # else `claude -p` can wait on stdin
    ms = round((time.monotonic() - t0) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(proc.stderr or proc.stdout)[-300:]}")
    out = json.loads(proc.stdout)
    text = (out.get("result") or "").strip()
    usage = out.get("usage") or {}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        parsed = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        parsed = {}
    return parsed, {"latency_ms": ms, "input_tokens": usage.get("input_tokens") or 0,
                    "output_tokens": usage.get("output_tokens") or 0,
                    "cost_usd": round(float(out.get("total_cost_usd") or 0), 7), "provider": "claude",
                    "reply_chars": len(text), "parsed": bool(parsed.get("placements"))}


PROVIDERS = {"arcee": _ask, "claude": _ask_claude}


def _clean(p: dict) -> dict | None:
    try:
        rot = int(round(float(p.get("rotation", 0)) / 90.0)) * 90 % 360
        return {"x_in": round(float(p["x_in"]), 1), "z_in": round(float(p["z_in"]), 1), "rotation": rot,
                "why": str(p.get("why", ""))[:120]}
    except (KeyError, TypeError, ValueError):
        return None


def _try(room: dict, lay: list[dict], product: dict, spot: dict) -> tuple[bool, list[dict], list[str]]:
    """Check one proposed spot. Accept only if every item in the room still reads 'fits' (find_spot's rule)."""
    trial = add_product(lay, product, spot["x_in"], spot["z_in"], spot["rotation"])
    res = check_layout(room, trial)
    bad = [f'{r["check"]}: {r["math"]}' for rs in res.values() for r in rs if r["verdict"] != FITS]
    return (not bad), res[product["id"]], bad


def plan_layout(room: dict, picks: list[dict], model: str | None = None, ask=None, provider: str | None = None) -> dict:
    """picks = [{"slot", "product"}] with catalog products. Returns placements plus the record of every call.

    provider: "arcee" (default) or "claude" (the local, signed-in Claude Code); also LAYOUT_PROVIDER in the env.
    `ask` can be replaced in tests with a function that returns canned proposals.
    """
    provider = (provider or os.environ.get("LAYOUT_PROVIDER") or "arcee").lower()
    if provider not in PROVIDERS:
        raise ValueError(f"unknown layout provider {provider!r}; use one of {sorted(PROVIDERS)}")
    if ask is None:
        ask = PROVIDERS[provider]
    model = model or (_model() if provider == "arcee" else "claude")
    by_id = {p["product"]["id"]: p for p in picks}
    to_place = [{"id": p["product"]["id"], "slot": p["slot"], "name": p["product"]["name"],
                 "category": p["product"]["category"], "w_in": p["product"]["dims_in"]["w"],
                 "d_in": p["product"]["dims_in"]["d"], "h_in": p["product"]["dims_in"]["h"]} for p in picks]
    facts = {**room_facts(room), "to_place": to_place, "rules": RULES}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(facts)}]
    calls, lay = [], layout_from_scan(room)
    done: dict[str, dict] = {}
    rejected: dict[str, list[dict]] = {pid: [] for pid in by_id}

    for round_no in (1, 2):
        pending = [pid for pid in by_id if pid not in done]
        if not pending:
            break
        try:
            parsed, call = ask(messages, model)
        except Exception as e:  # network or API error: fall through to find_spot
            calls.append({"round": round_no, "error": f"{type(e).__name__}: {e}"[:200]})
            break
        calls.append({"round": round_no, **call})
        proposals = {str(p.get("id")): _clean(p) for p in parsed.get("placements", []) if isinstance(p, dict)}
        failures = {}
        for pid in pending:  # plan order: the big pieces first
            spot = proposals.get(pid)
            if not spot:
                failures[pid] = ["no placement was given for this id"]
                continue
            ok, results, bad = _try(room, lay, by_id[pid]["product"], spot)
            if ok:
                lay = add_product(lay, by_id[pid]["product"], spot["x_in"], spot["z_in"], spot["rotation"])
                done[pid] = {**spot, "by": provider if round_no == 1 else f"{provider} (2nd try)", "results": results}
            else:
                rejected[pid].append({**spot, "round": round_no, "failed": bad[:4]})
                failures[pid] = bad[:4]
        if failures and round_no == 1:
            messages = messages + [
                {"role": "assistant", "content": json.dumps({"placements": [
                    {"id": pid, **{k: v for k, v in (proposals.get(pid) or {}).items() if k != "why"}} for pid in by_id]})},
                {"role": "user", "content": json.dumps({
                    "accepted": {pid: {k: done[pid][k] for k in ("x_in", "z_in", "rotation")} for pid in done},
                    "failed_checks": failures,
                    "instruction": "Keep the accepted pieces where they are. Give new placements ONLY for the failed "
                                   "ids, fixing the failed checks. Same JSON format."})}]

    for pid in by_id:  # whatever Arcee could not place legally: the deterministic search
        if pid in done:
            continue
        spot = find_spot(room, lay, by_id[pid]["product"])
        if spot:
            lay = add_product(lay, by_id[pid]["product"], spot["x_in"], spot["z_in"], spot["rotation"])
            done[pid] = {"x_in": spot["x_in"], "z_in": spot["z_in"], "rotation": spot["rotation"],
                         "why": f"placed by fit.layout.find_spot after {provider}'s proposals failed the checks",
                         "by": "find_spot", "results": spot["results"]}

    placements = [{"slot": by_id[pid]["slot"], "product_id": pid, "name": by_id[pid]["product"]["name"],
                   **(done.get(pid) or {"by": "unplaced", "why": "no spot passes every check", "results": []}),
                   "rejected_proposals": rejected[pid]} for pid in by_id]
    count = lambda label: sum(1 for p in placements if p["by"] == label)  # noqa: E731
    return {
        "provider": provider, "model": model, "calls": calls,
        "cost_usd": round(sum(c.get("cost_usd", 0) for c in calls), 7),
        "latency_ms": sum(c.get("latency_ms", 0) for c in calls),
        "summary": {"pieces": len(placements), "first_try": count(provider),
                    "second_try": count(f"{provider} (2nd try)"), "find_spot_fallback": count("find_spot"),
                    # old names kept so existing callers/tests don't break
                    "arcee_first_try": count(provider), "arcee_second_try": count(f"{provider} (2nd try)"),
                    "unplaced": count("unplaced"),
                    "proposals_rejected_by_fit_checks": sum(len(v) for v in rejected.values())},
        "placements": placements,
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    opt = {argv[i][2:]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
    args = [a for a in args if a not in opt.values()]
    if not args:
        print(__doc__)
        return 2
    plan_path = Path(args[0])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    scan = opt.get("scan", DEFAULT_SCAN)
    room = load_scan(str(ROOT / scan))
    catalog = {p["id"]: p for p in json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))["products"]}
    picks = [{"slot": it["slot"], "product": catalog[it["product_id"]]} for it in plan["items"] if it["product_id"] in catalog]
    out = plan_layout(room, picks, opt.get("model"), provider=opt.get("provider"))
    result = {
        "about": "Where each picked piece goes in the scanned room. Arcee proposed; fit.layout checked every "
                 "proposal; find_spot placed whatever failed. Written by python3 -m agent.arcee_layout.",
        "plan": plan_path.name, "plan_id": plan.get("plan_id"), "scan": scan, **out,
    }
    name = plan_path.stem.replace("plan.", "layout.", 1) if plan_path.stem.startswith("plan.") else f"layout.{plan_path.stem}"
    dest = Path(opt["out"]) if "out" in opt else plan_path.with_name(name + ".json")
    dest.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("model", "cost_usd", "latency_ms", "summary", "calls")}, indent=1))
    for p in result["placements"]:
        spot = f'x {p["x_in"]:>6} z {p["z_in"]:>6} rot {p["rotation"]:>3}' if "x_in" in p else "unplaced".ljust(26)
        print(f'  {p["slot"]:13} {spot}  by {p["by"]:15} rejected proposals: {len(p["rejected_proposals"])}')
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
