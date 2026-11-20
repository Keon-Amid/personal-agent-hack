"""Fit checks: does a real product fit the room? Pure Python, no dependencies.

Every check returns a dict that goes straight into the audit trail:
    {"check", "verdict", "math", "need_in", "available": {value_in, error_in, source}, "margin_in"}

verdict is one of:
    "fits"    - fits even if the measurement is off by its full error
    "unsure"  - fits or not depending on the error; ask the person to measure this one thing
    "no_fit"  - doesn't fit even in the best case

All lengths are inches.
"""

from __future__ import annotations

FITS, UNSURE, NO_FIT = "fits", "unsure", "no_fit"

DEFAULT_WALL_CLEARANCE_IN = 0.0  # extra space wanted beside the item on a wall
DEFAULT_WALKWAY_IN = 36.0        # clear path in front of an item placed against a wall


def measurement(value_in: float, error_in: float = 0.0, source: str = "user") -> dict:
    """A room measurement with where it came from and how far off it might be.

    source examples: "user" (typed in, error 0), "estimated:door", "estimated:paper".
    """
    if value_in <= 0 or error_in < 0:
        raise ValueError(f"bad measurement: value={value_in} error={error_in}")
    return {"value_in": float(value_in), "error_in": float(error_in), "source": source}


def _verdict(need: float, m: dict) -> tuple[str, float]:
    lo = m["value_in"] - m["error_in"]
    hi = m["value_in"] + m["error_in"]
    if need <= lo:
        v = FITS
    elif need > hi:
        v = NO_FIT
    else:
        v = UNSURE
    return v, round(m["value_in"] - need, 2)


def _avail(m: dict) -> str:
    s = f'{m["value_in"]:g} in'
    if m["error_in"]:
        s += f' ±{m["error_in"]:g}'
    return f'{s} ({m["source"]})'


def _result(check: str, need: float, m: dict, math: str) -> dict:
    v, margin = _verdict(need, m)
    sym = {"fits": "≤", "no_fit": ">", "unsure": "≈"}[v]
    return {
        "check": check,
        "verdict": v,
        "math": (f"{math} = {need:g} in" if "+" in math else math) + f" {sym} {_avail(m)}",
        "need_in": round(need, 2),
        "available": dict(m),
        "margin_in": margin,
    }


def check_wall(item: dict, wall: dict, clearance_in: float = DEFAULT_WALL_CLEARANCE_IN) -> dict:
    """Item width (+ clearance) along a wall."""
    w = item["dims_in"]["w"]
    need = w + clearance_in
    math = f"width {w:g} in" + (f" + clearance {clearance_in:g} in" if clearance_in else "")
    return _result("wall", need, wall, math)


def check_floor(item: dict, room_depth: dict, walkway_in: float = DEFAULT_WALKWAY_IN) -> dict:
    """Item placed against a wall: its depth plus a walkway must fit the room's depth from that wall."""
    d = item["dims_in"]["d"]
    need = d + walkway_in
    return _result("floor", need, room_depth, f"depth {d:g} in + walkway {walkway_in:g} in")


def check_doorway(item: dict, door_width: dict, door_height: dict) -> list[dict]:
    """Can every box (or the assembled item, if it ships assembled) get through the door?

    A box goes through if its smallest side fits the door width and its middle side fits the door
    height (carried on edge). Returns one result per box; the item gets through only if all fit.
    """
    boxes = item.get("packages_in") or [item["dims_in"]]
    out = []
    for i, b in enumerate(boxes, 1):
        a, mid, _ = sorted([b["w"], b["d"], b["h"]])
        label = f"box {i}/{len(boxes)}" if item.get("packages_in") else "assembled item"
        r_w = _result("doorway_width", a, door_width, f"{label} smallest side {a:g} in")
        r_h = _result("doorway_height", mid, door_height, f"{label} middle side {mid:g} in")
        out += [r_w, r_h]
    return out


def overall(results: list[dict]) -> str:
    """Worst verdict across several checks: one no_fit sinks it, one unsure makes it unsure."""
    vs = {r["verdict"] for r in results}
    return NO_FIT if NO_FIT in vs else UNSURE if UNSURE in vs else FITS
