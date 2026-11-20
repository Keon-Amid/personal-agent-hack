"""Find where the room sits inside a raw LiDAR scan, so the 3D renderer can put furniture in it.

  python3 scripts/scan_align.py [assets/room_scan_geometry.glb] [contracts/plan.room_scan.json]

Writes <scan>.align.json next to the scan: the floor height and the positions of the four wall planes, in the
scan's own coordinates (metres, Y up). Method (same idea as assets/README.md): histogram the mesh's points in
2 cm bins. The floor is the lowest strong peak in height. For each horizontal axis, take the points at
mid-height and pick the pair of strong peaks whose spacing is closest to the room's measured wall / depth from
the plan. Assumes the scan is axis-aligned, which this one is. Needs numpy.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BIN = 0.02


def positions(path: Path) -> np.ndarray:
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + n])
    blob = data[20 + n + 8:]
    out = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            view = doc["bufferViews"][acc["bufferView"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            raw = np.frombuffer(blob, dtype=np.uint8, count=stride * acc["count"], offset=start)
            out.append(raw.reshape(acc["count"], stride)[:, :12].copy().view("<f4").reshape(-1, 3))
    return np.concatenate(out)


def peaks(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lo = np.floor(values.min() / BIN) * BIN
    counts, edges = np.histogram(values, bins=np.arange(lo, values.max() + 2 * BIN, BIN))
    return counts, edges[:-1] + BIN / 2


def wall_pair(values: np.ndarray, target_m: float) -> tuple[float, float, int, int]:
    counts, centres = peaks(values)
    strong = [i for i in range(len(counts)) if counts[i] >= 0.2 * counts.max()
              and counts[i] == counts[max(0, i - 3):i + 4].max()]
    best = min(((abs((centres[b] - centres[a]) - target_m), a, b) for a in strong for b in strong if b > a),
               key=lambda t: t[0])
    _, a, b = best
    return float(centres[a]), float(centres[b]), int(counts[a]), int(counts[b])


def main(argv: list[str]) -> None:
    scan = Path(argv[0]) if argv else ROOT / "assets" / "room_scan_geometry.glb"
    plan_path = Path(argv[1]) if len(argv) > 1 else ROOT / "contracts" / "plan.room_scan.json"
    room = json.loads(plan_path.read_text(encoding="utf-8"))["room"]
    wall_m, depth_m = room["wall"]["value_in"] * 0.0254, room["depth"]["value_in"] * 0.0254
    p = positions(scan)

    cy, ys = peaks(p[:, 1])
    strong_y = [i for i in range(len(cy)) if cy[i] >= 0.3 * cy.max()]
    floor, ceiling = float(ys[strong_y[0]]), float(ys[strong_y[-1]])
    mid = p[(p[:, 1] > floor + 0.9) & (p[:, 1] < floor + 1.8)]

    # Which horizontal axis carries the long wall? Try both and keep the better match.
    fits = {}
    for name, (ax_wall, ax_depth) in {"wall_along_x": (0, 2), "wall_along_z": (2, 0)}.items():
        a0, a1, na0, na1 = wall_pair(mid[:, ax_wall], wall_m)
        b0, b1, nb0, nb1 = wall_pair(mid[:, ax_depth], depth_m)
        err = abs((a1 - a0) - wall_m) + abs((b1 - b0) - depth_m)
        fits[name] = (err, {"along": [a0, a1], "along_points": [na0, na1], "across": [b0, b1], "across_points": [nb0, nb1]})
    name, (err, f) = min(fits.items(), key=lambda kv: kv[1][0])
    # The wall furniture goes against: the more solid of the two long walls (more scan points = fewer openings).
    back_is_low = f["across_points"][0] >= f["across_points"][1]

    out = {
        "about": "Where the room sits in the scan's own coordinates (metres, Y up). Written by scripts/scan_align.py.",
        "scan": scan.name, "plan": plan_path.name, "points": int(len(p)),
        "orientation": name, "floor_m": round(floor, 3), "ceiling_m": round(ceiling, 3),
        "wall_ends_m": [round(v, 3) for v in f["along"]],        # the two side walls, along the long wall
        "depth_ends_m": [round(v, 3) for v in f["across"]],      # the two long walls
        "back_wall_m": round(f["across"][0] if back_is_low else f["across"][1], 3),
        "back_wall_is_low_end": back_is_low,
        "measured_in": {"wall": round((f["along"][1] - f["along"][0]) / 0.0254, 1),
                        "depth": round((f["across"][1] - f["across"][0]) / 0.0254, 1),
                        "ceiling": round((ceiling - floor) / 0.0254, 1)},
        "plan_in": {"wall": room["wall"]["value_in"], "depth": room["depth"]["value_in"]},
        "wall_points": {"side_walls": f["along_points"], "long_walls": f["across_points"]},
    }
    dest = scan.with_suffix(".align.json")
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    print("wrote", dest)


if __name__ == "__main__":
    main(sys.argv[1:])
