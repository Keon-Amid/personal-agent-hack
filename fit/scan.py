"""Read a RoomPlan scan (Polycam "Floorplan"/room mode, exported as GLB) into a room model.

RoomPlan names every object: Wall_0, Door_0, table_other_rect_0, chair_dining_four_back_arms_1, television_0, ...
Polycam writes each object's vertices in room coordinates (meters, Y up), so an object's bounding box is its
position and size. Stdlib only.

    room = load_scan("assets/room_scan_roomplan.glb")
    room["walls"]  -> [{"id", "a": [x, z], "b": [x, z], "length_in"}]          (inches, floor plane)
    room["doors"]  -> [{"id", "center": [x, z], "width_in", "height_in", "wall", "axis"}]
    room["items"]  -> [{"id", "label", "category", "x_in", "z_in", "w_in", "d_in", "h_in", "bottom_in",
                        "rotation": 0, "kind": "existing", "on_floor"}]
    room["outline"] -> [[x, z], ...] interior polygon from the walls (inches)
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

M_TO_IN = 39.3701

# RoomPlan label prefix -> our category (catalog categories where one exists)
CATEGORY = [
    ("chair_dining", "dining_chair"), ("chair_swivel", "desk_chair"), ("chair", "armchair"),
    ("sofa", "sofa"), ("table_dining", "dining_table"), ("table_coffee", "coffee_table"), ("table", "table"),
    ("bed", "bed"), ("storage", "storage"), ("television", "television"), ("refrigerator", "appliance"),
    ("stove", "appliance"), ("oven", "appliance"), ("washer", "appliance"), ("dishwasher", "appliance"),
    ("sink", "fixture"), ("toilet", "fixture"), ("bathtub", "fixture"), ("fireplace", "fixture"),
]


def _glb(path: str | Path) -> tuple[dict, bytes]:
    b = Path(path).read_bytes()
    magic, _, _ = struct.unpack_from("<4sII", b, 0)
    if magic != b"glTF":
        raise ValueError(f"{path} is not a GLB file")
    clen = struct.unpack_from("<I", b, 12)[0]
    return json.loads(b[20:20 + clen]), b


def _bbox(j: dict, mesh: int) -> tuple[list[float], list[float]]:
    lo, hi = [1e9] * 3, [-1e9] * 3
    for prim in j["meshes"][mesh]["primitives"]:
        a = j["accessors"][prim["attributes"]["POSITION"]]
        lo = [min(x, y) for x, y in zip(lo, a["min"])]
        hi = [max(x, y) for x, y in zip(hi, a["max"])]
    return lo, hi


def _category(label: str) -> str:
    for prefix, cat in CATEGORY:
        if label.startswith(prefix):
            return cat
    return label.split("_")[0]


def _chain(segments: list[tuple[list[float], list[float]]], tol: float = 0.25) -> list[list[float]]:
    """Order wall centre-line segments into a closed loop of corner points (meters)."""
    if not segments:
        return []
    segs = [list(s) for s in segments]
    poly = [segs[0][0], segs[0][1]]
    used = {0}
    while len(used) < len(segs):
        end = poly[-1]
        best = None
        for i, (a, b) in enumerate(segs):
            if i in used:
                continue
            for p, q in ((a, b), (b, a)):
                dist = abs(p[0] - end[0]) + abs(p[1] - end[1])
                if dist < tol and (best is None or dist < best[0]):
                    best = (dist, i, q)
        if best is None:
            break
        used.add(best[1])
        poly.append(best[2])
    if len(poly) > 2 and abs(poly[0][0] - poly[-1][0]) + abs(poly[0][1] - poly[-1][1]) < tol:
        poly.pop()
    return poly


def load_scan(path: str | Path) -> dict:
    j, _ = _glb(path)
    nodes = j.get("nodes", [])
    if any(k in n for n in nodes for k in ("translation", "rotation", "scale", "matrix")):
        raise ValueError("scan has node transforms; this reader expects Polycam's world-space vertices")
    floor_y = None
    for n in nodes:
        if (n.get("name") or "").startswith("Floor_") and "mesh" in n:
            floor_y = _bbox(j, n["mesh"])[1][1]
    floor_y = 0.0 if floor_y is None else floor_y

    walls, wall_segs, doors, items = [], [], [], []
    for n in nodes:
        name, mesh = n.get("name") or "", n.get("mesh")
        if mesh is None:
            continue
        lo, hi = _bbox(j, mesh)
        dx, dz = hi[0] - lo[0], hi[2] - lo[2]
        if re.fullmatch(r"Wall_\d+", name):
            if dx >= dz:  # runs along x
                zc = (lo[2] + hi[2]) / 2
                a, b = [lo[0] + dz / 2, zc], [hi[0] - dz / 2, zc]
            else:
                xc = (lo[0] + hi[0]) / 2
                a, b = [xc, lo[2] + dx / 2], [xc, hi[2] - dx / 2]
            wall_segs.append((a, b))
            walls.append({"id": name, "a": [round(v * M_TO_IN, 1) for v in a], "b": [round(v * M_TO_IN, 1) for v in b],
                          "length_in": round(max(dx, dz) * M_TO_IN - min(dx, dz) * M_TO_IN, 1)})
        elif re.fullmatch(r"(Door|Opening|Window)_\d+", name):
            axis = "z" if dx < dz else "x"  # the door lies in a wall that runs along this axis
            width = max(dx, dz)
            doors.append({"id": name, "kind": name.split("_")[0].lower(),
                          "center": [round((lo[0] + hi[0]) / 2 * M_TO_IN, 1), round((lo[2] + hi[2]) / 2 * M_TO_IN, 1)],
                          "width_in": round(width * M_TO_IN, 1), "height_in": round((hi[1] - lo[1]) * M_TO_IN, 1),
                          "axis": axis})
        elif re.search(r"_\d+$", name) and not re.match(r"(Joint|Floor|Ceiling)_", name):
            bottom = (lo[1] - floor_y) * M_TO_IN
            items.append({
                "id": name, "label": re.sub(r"_\d+$", "", name), "category": _category(name),
                "x_in": round((lo[0] + hi[0]) / 2 * M_TO_IN, 1), "z_in": round((lo[2] + hi[2]) / 2 * M_TO_IN, 1),
                "w_in": round(dx * M_TO_IN, 1), "d_in": round(dz * M_TO_IN, 1),
                "h_in": round((hi[1] - lo[1]) * M_TO_IN, 1), "bottom_in": round(bottom, 1),
                "rotation": 0, "kind": "existing", "on_floor": bottom < 6,
            })
    outline = [[round(x * M_TO_IN, 1), round(z * M_TO_IN, 1)] for x, z in _chain(wall_segs)]
    # each door: which wall it sits in, and the direction into the room (sign along the wall's normal)
    for d in doors:
        cx, cz = d["center"]
        best = min(walls, key=lambda w: _dist_to_segment((cx, cz), w["a"], w["b"]))
        d["wall"] = best["id"]
        nx, nz = (1, 0) if d["axis"] == "z" else (0, 1)
        d["into_room"] = [nx, nz] if point_in_poly((cx + nx * 12, cz + nz * 12), outline) else [-nx, -nz]
    return {"source": str(path), "units": "inches", "walls": walls, "doors": doors, "items": items,
            "outline": outline}


def _dist_to_segment(p, a, b) -> float:
    (px, pz), (ax, az), (bx, bz) = p, a, b
    vx, vz = bx - ax, bz - az
    L = vx * vx + vz * vz
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * vx + (pz - az) * vz) / L))
    return ((px - ax - t * vx) ** 2 + (pz - az - t * vz) ** 2) ** 0.5


def point_in_poly(p, poly) -> bool:
    x, z = p
    inside = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            inside = not inside
    return inside


if __name__ == "__main__":
    import sys
    print(json.dumps(load_scan(sys.argv[1] if len(sys.argv) > 1 else "assets/room_scan_roomplan.glb"), indent=1))
