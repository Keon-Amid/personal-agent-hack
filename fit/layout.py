"""Position-aware checks for rearranging a scanned room (fit.scan.load_scan output).

A layout is the room's items with positions (inches, floor plane x/z, item centre) and rotation (0/90/180/270).
Every check returns FitResult-shaped dicts ({"check", "verdict", "math", ...}) so the audit trail and UI treat
them like the other fit checks.

    lay = layout_from_scan(room)                       # existing furniture where the scan found it
    lay = add_product(lay, product, x_in, z_in, rot)   # an IKEA product from data/products.json
    lay, results = move(room, lay, item_id, x_in, z_in, rotation)
    check_layout(room, lay) -> {item_id: [FitResult]}

Checks per floor item:
  in_room    every footprint corner inside the walls (the scan's outline)
  overlap    footprint doesn't overlap another floor item (chairs may tuck under tables; anything may stand on a rug)
  door_swing nothing on the floor inside the door's swing (a door-width square in front of it)
  clearance  at least 18 in to other floor items / walls on some side to get to it ("unsure" if tighter)
Wall-mounted items (bottom > 24 in, e.g. the TV) are skipped for floor checks.
"""
from __future__ import annotations

import copy

from .checks import FITS, NO_FIT, UNSURE
from .scan import point_in_poly

CLEARANCE_IN = 18.0  # minimum gap to reach an item (team default, not a code)
RUG_MARGIN_IN = 6.0  # same as fit.checks.DEFAULT_RUG_MARGIN_IN
TUCK_UNDER = {("dining_chair", "table"), ("dining_chair", "dining_table"), ("desk_chair", "table"),
              ("desk_chair", "desk"), ("desk_chair", "dining_table"), ("armchair", "coffee_table")}


def _footprint(it: dict) -> tuple[float, float, float, float]:
    w, d = (it["d_in"], it["w_in"]) if it.get("rotation", 0) % 180 == 90 else (it["w_in"], it["d_in"])
    return it["x_in"] - w / 2, it["z_in"] - d / 2, it["x_in"] + w / 2, it["z_in"] + d / 2


def _on_floor(it: dict) -> bool:
    return it.get("bottom_in", 0) < 24


def _shares_floor(a: dict, b: dict) -> bool:
    """Items that may share floor space: chairs tucked under tables, anything standing on a rug."""
    pair = (a["category"], b["category"])
    return "rug" in pair or pair in TUCK_UNDER or pair[::-1] in TUCK_UNDER


def _overlap(a, b) -> tuple[float, float]:
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def layout_from_scan(room: dict) -> list[dict]:
    return copy.deepcopy(room["items"])


def add_product(lay: list[dict], product: dict, x_in: float, z_in: float, rotation: int = 0) -> list[dict]:
    d = product["dims_in"]
    item = {"id": product["id"], "label": product["name"], "category": product["category"],
            "x_in": float(x_in), "z_in": float(z_in), "w_in": d["w"], "d_in": d["d"], "h_in": d["h"] or 0,
            "bottom_in": 0, "rotation": rotation % 360, "kind": "new", "on_floor": True,
            "source_url": product.get("source_url")}
    return [i for i in lay if i["id"] != product["id"]] + [item]


def _res(check: str, verdict: str, math: str, **kw) -> dict:
    return {"check": check, "verdict": verdict, "math": math, **kw}


def door_zone(door: dict) -> tuple[float, float, float, float]:
    """Square of side door width, in front of the door on the room side."""
    cx, cz = door["center"]
    w = door["width_in"]
    nx, nz = door["into_room"]
    if door["axis"] == "z":  # door runs along z, opens along x
        x0 = cx if nx > 0 else cx - w
        return x0, cz - w / 2, x0 + w, cz + w / 2
    z0 = cz if nz > 0 else cz - w
    return cx - w / 2, z0, cx + w / 2, z0 + w


def check_item(room: dict, lay: list[dict], it: dict) -> list[dict]:
    if not _on_floor(it):
        return [_res("in_room", FITS, f'{it["label"]} is wall-mounted ({it["bottom_in"]:g} in up); floor checks skipped')]
    fp = _footprint(it)
    out = []
    m = RUG_MARGIN_IN if it["category"] == "rug" else 0.0  # team rule: rugs stay 6 in from every wall
    corners = [(fp[0] - m, fp[1] - m), (fp[2] + m, fp[1] - m), (fp[2] + m, fp[3] + m), (fp[0] - m, fp[3] + m)]
    outside = [c for c in corners if not point_in_poly(c, room["outline"])]
    within = f" (with the {m:g} in rug margin)" if m else ""
    out.append(_res("in_room", NO_FIT if outside else FITS,
                    f'corner ({outside[0][0]:.0f}, {outside[0][1]:.0f}) in is outside the walls{within}' if outside
                    else f"all four corners inside the walls{within}"))
    for other in lay:
        if other["id"] == it["id"] or not _on_floor(other):
            continue
        ox, oz = _overlap(fp, _footprint(other))
        if ox > 0.5 and oz > 0.5:
            if _shares_floor(it, other):
                continue
            out.append(_res("overlap", NO_FIT, f'overlaps {other["label"]} ({other["id"]}) by {ox:.0f} x {oz:.0f} in',
                            with_id=other["id"]))
    for door in ([] if it["category"] == "rug" else room["doors"]):  # a flat rug doesn't stop a door
        dz = door_zone(door)
        ox, oz = _overlap(fp, dz)
        if ox > 0.5 and oz > 0.5:
            out.append(_res("door_swing", NO_FIT,
                            f'blocks the {door["width_in"]:g} in door swing ({door["id"]}) by {ox:.0f} x {oz:.0f} in'))
    # clearance: the widest free gap on any of the 4 sides (to walls' outline box or other floor items)
    xs = [p[0] for p in room["outline"]]
    zs = [p[1] for p in room["outline"]]
    gaps = {"left": fp[0] - min(xs), "right": max(xs) - fp[2], "back": fp[1] - min(zs), "front": max(zs) - fp[3]}
    for other in lay:
        if other["id"] == it["id"] or not _on_floor(other):
            continue
        o = _footprint(other)
        if _shares_floor(it, other):
            continue
        if o[1] < fp[3] and o[3] > fp[1]:  # overlaps in z -> blocks left/right
            if o[2] <= fp[0]:
                gaps["left"] = min(gaps["left"], fp[0] - o[2])
            if o[0] >= fp[2]:
                gaps["right"] = min(gaps["right"], o[0] - fp[2])
        if o[0] < fp[2] and o[2] > fp[0]:  # overlaps in x -> blocks back/front
            if o[3] <= fp[1]:
                gaps["back"] = min(gaps["back"], fp[1] - o[3])
            if o[1] >= fp[3]:
                gaps["front"] = min(gaps["front"], o[1] - fp[3])
    side, best = max(gaps.items(), key=lambda kv: kv[1])
    out.append(_res("clearance", FITS if best >= CLEARANCE_IN else UNSURE,
                    f'widest gap {best:.0f} in ({side}) {"≥" if best >= CLEARANCE_IN else "<"} {CLEARANCE_IN:g} in to reach it',
                    gap_in=round(best, 1)))
    return out


def check_layout(room: dict, lay: list[dict]) -> dict:
    return {it["id"]: check_item(room, lay, it) for it in lay}


def find_spot(room: dict, lay: list[dict], product: dict, step_in: float = 6.0) -> dict | None:
    """Search the room for a place where `product` passes every check, preferring spots against a wall.

    Tries every position on a `step_in` grid at 0° and 90°; keeps spots where the product and every existing item
    still check out (all `fits`). Returns {"x_in", "z_in", "rotation", "wall_gap_in", "results"} for the spot
    closest to a wall (sofas, dressers and shelves go against walls), or None if nothing fits anywhere.
    """
    xs = [p[0] for p in room["outline"]]
    zs = [p[1] for p in room["outline"]]
    d = product["dims_in"]
    best = None
    for rot in (0, 90):
        w, dd = (d["d"], d["w"]) if rot == 90 else (d["w"], d["d"])
        x = min(xs) + w / 2
        while x <= max(xs) - w / 2:
            z = min(zs) + dd / 2
            while z <= max(zs) - dd / 2:
                trial = add_product(lay, product, x, z, rot)
                res = check_layout(room, trial)
                if all(r["verdict"] == FITS for rs in res.values() for r in rs):
                    gap = min(x - w / 2 - min(xs), max(xs) - x - w / 2, z - dd / 2 - min(zs), max(zs) - z - dd / 2)
                    if best is None or gap < best["wall_gap_in"]:
                        best = {"x_in": round(x, 1), "z_in": round(z, 1), "rotation": rot,
                                "wall_gap_in": round(gap, 1), "results": res[product["id"]]}
                z += step_in
            x += step_in
    return best


def move(room: dict, lay: list[dict], item_id: str, x_in: float, z_in: float, rotation: int | None = None):
    new = copy.deepcopy(lay)
    for it in new:
        if it["id"] == item_id:
            it["x_in"], it["z_in"] = float(x_in), float(z_in)
            if rotation is not None:
                it["rotation"] = rotation % 360
            break
    else:
        raise KeyError(item_id)
    return new, check_layout(room, new)
