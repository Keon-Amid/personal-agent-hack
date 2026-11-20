"""agent.arcee_layout without the network: a fake model returns canned proposals, fit.layout does the real checks."""
import json
from pathlib import Path

from fit.layout import add_product, find_spot, layout_from_scan
from fit.scan import load_scan

from agent.arcee_layout import plan_layout

ROOT = Path(__file__).resolve().parent.parent
CATALOG = {p["id"]: p for p in json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))["products"]}
PLAN = json.loads((ROOT / "contracts" / "plan.room_scan.json").read_text(encoding="utf-8"))
PICKS = [{"slot": it["slot"], "product": CATALOG[it["product_id"]]} for it in PLAN["items"]]
CALL = {"latency_ms": 1, "input_tokens": 10, "output_tokens": 10, "cost_usd": 0.0001}


def room():
    return load_scan(str(ROOT / "assets" / "room_scan_roomplan.glb"))


def legal_spots(rm):
    """Spots that really pass every check, found the deterministic way, to use as a 'good' proposal."""
    lay, out = layout_from_scan(rm), {}
    for p in PICKS:
        s = find_spot(rm, lay, p["product"])
        lay = add_product(lay, p["product"], s["x_in"], s["z_in"], s["rotation"])
        out[p["product"]["id"]] = {"id": p["product"]["id"], "x_in": s["x_in"], "z_in": s["z_in"], "rotation": s["rotation"]}
    return out


def test_good_proposals_are_accepted_as_arcee():
    rm = room()
    good = legal_spots(rm)
    out = plan_layout(rm, PICKS, model="fake", ask=lambda messages, model: ({"placements": list(good.values())}, CALL))
    assert out["summary"]["arcee_first_try"] == len(PICKS)
    assert out["summary"]["find_spot_fallback"] == 0
    assert len(out["calls"]) == 1 and out["cost_usd"] == 0.0001


def test_bad_proposal_is_rejected_with_the_math_then_fixed_on_second_try():
    rm = room()
    good = legal_spots(rm)
    sofa = PICKS[0]["product"]["id"]
    xs = [p[0] for p in rm["outline"]]
    outside = {"id": sofa, "x_in": max(xs) + 500, "z_in": 0, "rotation": 0}
    replies = [{"placements": [outside] + [v for k, v in good.items() if k != sofa]}, {"placements": [good[sofa]]}]
    seen = []

    def ask(messages, model):
        seen.append(messages)
        return replies[len(seen) - 1], CALL

    out = plan_layout(rm, PICKS, model="fake", ask=ask)
    first = next(p for p in out["placements"] if p["product_id"] == sofa)
    assert first["rejected_proposals"] and "in_room" in first["rejected_proposals"][0]["failed"][0]
    assert out["summary"]["unplaced"] == 0
    assert out["summary"]["proposals_rejected_by_fit_checks"] >= 1
    assert len(seen) == 2 and "failed_checks" in seen[1][-1]["content"]  # the failing maths went back to the model
    assert first["by"] in ("arcee (2nd try)", "find_spot")  # accepted only if it passes every check


def test_model_that_never_gives_a_legal_spot_falls_back_to_find_spot():
    rm = room()
    xs = [p[0] for p in rm["outline"]]
    junk = {"placements": [{"id": p["product"]["id"], "x_in": max(xs) + 500, "z_in": 0, "rotation": 0} for p in PICKS]}
    out = plan_layout(rm, PICKS, model="fake", ask=lambda messages, model: (junk, CALL))
    assert out["summary"]["arcee_first_try"] == 0 and out["summary"]["arcee_second_try"] == 0
    assert out["summary"]["find_spot_fallback"] == len(PICKS)
    assert all(p["by"] == "find_spot" for p in out["placements"])


def test_api_error_or_garbage_reply_never_breaks_the_plan():
    rm = room()

    def boom(messages, model):
        raise RuntimeError("ARCEE_API_KEY is not set")

    out = plan_layout(rm, PICKS, model="fake", ask=boom)
    assert out["calls"][0]["error"].startswith("RuntimeError")
    assert out["summary"]["find_spot_fallback"] == len(PICKS)
    out = plan_layout(rm, PICKS, model="fake", ask=lambda messages, model: ({}, CALL))
    assert out["summary"]["find_spot_fallback"] == len(PICKS)
