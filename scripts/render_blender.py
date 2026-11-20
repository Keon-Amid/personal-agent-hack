"""Render the scanned room with the agent's picks, headless in Blender (stills for the demo video).

    /Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/render_blender.py -- \
        [--plan contracts/plan.room_scan.json] [--scan assets/room_scan_roomplan.glb] [--out renders/room]
        [--res 1920x1080] [--shots overview,sofa,door]

Writes <out>_before.png (the room as scanned, cut-away from above), <out>_after.png (same view with the agent's
products), <out>_sofa.png (eye level, facing the sofa) and <out>_door.png (eye level, from the doorway), plus
<out>.json with every placement. Positions are not invented: each product goes where fit.layout.find_spot says it fits (inside the
walls, clear of the door swing and the scanned furniture). Products use Kyle's models (web/public/models), stretched
to the catalog's W x D x H; rugs (no model) are flat boxes at their real size.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy  # Blender's Python
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fit.layout import add_product, find_spot, layout_from_scan  # noqa: E402
from fit.scan import load_scan, point_in_poly  # noqa: E402

IN = 0.0254  # inches -> meters
EYE_M = 1.55  # camera height for eye-level shots
EXPOSURE = -0.6


def args() -> dict:
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    get = lambda f, d: a[a.index(f) + 1] if f in a else d  # noqa: E731
    w, h = get("--res", "1920x1080").lower().split("x")
    return {"plan": ROOT / get("--plan", "contracts/plan.room_scan.json"),
            "scan": ROOT / get("--scan", "assets/room_scan_roomplan.glb"),
            "out": ROOT / get("--out", "renders/room"), "res": (int(w), int(h)),
            "shots": get("--shots", "overview,sofa,door").split(",")}


def place(room: dict, plan: dict, products: dict) -> list[dict]:
    """Put each planned product where it fits; furniture first, rugs last (they go under things)."""
    lay = layout_from_scan(room)
    placed = []
    for it in sorted(plan["items"], key=lambda i: products[i["product_id"]]["category"] == "rug"):
        p = products[it["product_id"]]
        spot = find_spot(room, lay, p)
        if spot is None:
            print(f"render: no spot where {p['name']} fits; left out")
            continue
        lay = add_product(lay, p, spot["x_in"], spot["z_in"], spot["rotation"])
        placed.append({"product_id": p["id"], "name": p["name"], "category": p["category"], "dims_in": p["dims_in"],
                       **{k: spot[k] for k in ("x_in", "z_in", "rotation", "wall_gap_in")}})
    return placed


def new_objects(before: set) -> list:
    return [o for o in bpy.data.objects if o.name not in before]


def bounds(objs) -> tuple[Vector, Vector]:
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def material(name: str, rgb: tuple, rough: float = 0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def add_model(item: dict, floor_z: float, models: dict) -> list:
    d = item["dims_in"]
    w, dd, h = d["w"] * IN, d["d"] * IN, max((d.get("h") or 0.5), 0.5) * IN
    entry = models.get(item["product_id"])
    before = {o.name for o in bpy.data.objects}
    if entry and (ROOT / "web/public/models" / entry["file"]).exists():
        bpy.ops.import_scene.gltf(filepath=str(ROOT / "web/public/models" / entry["file"]))
        objs = [o for o in new_objects(before) if o.type == "MESH"]
        for o in new_objects(before):
            o.select_set(o.type == "MESH")
        bpy.context.view_layer.objects.active = objs[0]
        if len(objs) > 1:
            bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.rotation_euler = (0, 0, math.radians(entry.get("rot_y_deg", 0)))  # model's own turn to match W/D
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        cur = obj.dimensions
        obj.scale = (w / cur.x, dd / cur.y, h / cur.z)  # stretch to the catalog's listed size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    else:  # no model (rugs): a box at the real size
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.active_object
        obj.scale = (w, dd, h)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material(f"mat_{item['product_id']}", (0.62, 0.42, 0.33)))
    obj.name = item["product_id"]
    # scan coords: x, z (glTF, Y up) -> Blender x, -y (Z up)
    obj.rotation_euler = (0, 0, math.radians(item["rotation"]))
    obj.location = (item["x_in"] * IN, -item["z_in"] * IN, floor_z + obj.dimensions.z / 2 + 0.002)
    return [obj]


def setup_scene(res: tuple[int, int], lo: Vector, hi: Vector, floor_z: float):
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.exposure = EXPOSURE  # darker than default so mid-grey fabric reads grey, not white
    world = bpy.data.worlds.new("w") if not sc.world else sc.world
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.85, 0.85, 0.83, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    centre = (lo + hi) / 2
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 1.5
    sun.rotation_euler = (math.radians(40), 0, math.radians(30))
    sc.collection.objects.link(sun)
    # room light just under the ceiling, so eye-level shots (ceiling on) are lit too
    area = bpy.data.objects.new("area", bpy.data.lights.new("area", "AREA"))
    area.data.energy, area.data.size = 220, 2.5
    area.location = (centre.x, centre.y, floor_z + 2.7)
    sc.collection.objects.link(area)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    target = bpy.data.objects.new("target", None)
    sc.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam, target


def _blocks(seg_a, seg_b, box) -> bool:
    """Does the 2D segment a->b pass through the box (x0, z0, x1, z1)? (Liang-Barsky clip)"""
    (ax, az), (bx, bz) = seg_a, seg_b
    t0, t1 = 0.0, 1.0
    for p, q in ((-(bx - ax), ax - box[0]), (bx - ax, box[2] - ax), (-(bz - az), az - box[1]), (bz - az, box[3] - az)):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def _clear_spot(back: str, sofa: dict, xs, zs, room: dict, placed: list) -> tuple[float, float]:
    """Camera spot 14 in inside the walls with a clear line of sight to the sofa, closest to facing it head-on.

    The sofa faces away from the wall behind it (`back`); candidates go all round the room's edge."""
    obstacles = []
    for it in room["items"] + [{**p, "w_in": p["dims_in"]["w"], "d_in": p["dims_in"]["d"]} for p in placed]:
        if it.get("category") == "rug" or it.get("product_id") == sofa["product_id"] or not it.get("on_floor", True):
            continue
        w, d = (it["d_in"], it["w_in"]) if it.get("rotation", 0) % 180 == 90 else (it["w_in"], it["d_in"])
        obstacles.append((it["x_in"] - w / 2, it["z_in"] - d / 2, it["x_in"] + w / 2, it["z_in"] + d / 2))
    sx, sz = sofa["x_in"], sofa["z_in"]
    face = {"x-": (1, 0), "x+": (-1, 0), "z-": (0, 1), "z+": (0, -1)}[back]
    x0, x1, z0, z1 = min(xs) + 14, max(xs) - 14, min(zs) + 14, max(zs) - 14
    cands = [(x0 + i * (x1 - x0) / 30, z) for i in range(31) for z in (z0, z1)] + \
            [(x, z0 + i * (z1 - z0) / 30) for i in range(31) for x in (x0, x1)]
    best = None
    for cx, cz in cands:
        vx, vz = cx - sx, cz - sz
        dist = (vx * vx + vz * vz) ** 0.5
        if dist < 60 or not point_in_poly((cx, cz), room["outline"]):
            continue
        if any(_blocks((cx, cz), (sx, sz), b) for b in obstacles):
            continue
        cos = (vx * face[0] + vz * face[1]) / dist  # 1 = straight in front of the sofa
        if cos > 0.2 and (best is None or cos > best[0]):
            best = (cos, (cx, cz))
    return best[1] if best else ((x1 if face[0] > 0 else x0) if face[0] else sx, (z1 if face[1] > 0 else z0) if face[1] else sz)


def shot(name: str, cam, target, lo: Vector, hi: Vector, floor_z: float, scan_objs: list, placed: list, room: dict):
    """Set the camera and what's visible for one named shot. Returns False if the shot can't be made."""
    centre = (lo + hi) / 2
    cutaway = name == "overview"
    for o in scan_objs:
        kind = o.name.split("_")[0]
        if kind == "Ceiling":
            o.hide_render = cutaway  # eye-level shots keep the ceiling
        elif kind in ("Wall", "Joint") and o.type == "MESH":
            wl, wh = bounds([o])
            c = (wl + wh) / 2
            thin_y = (wh.y - wl.y) < (wh.x - wl.x)
            o.hide_render = cutaway and ((thin_y and c.y < centre.y) or (not thin_y and c.x > centre.x))
    eye = floor_z + EYE_M
    if cutaway:
        span = max(hi.x - lo.x, hi.y - lo.y)
        cam.data.lens = 22
        cam.location = (centre.x + span * 0.55, centre.y - span * 0.75, floor_z + span * 0.95)
        target.location = (centre.x, centre.y, floor_z + 0.4)
        return True
    cam.data.lens = 16  # wide, like a phone's 0.5x
    if name == "sofa":
        sofa = next((p for p in placed if p["category"] == "sofa"), None)
        if not sofa:
            return False
        xs = [q[0] for q in room["outline"]]
        zs = [q[1] for q in room["outline"]]
        sx, sz = sofa["x_in"], sofa["z_in"]
        # the wall the sofa backs onto is the nearest one; stand by the opposite wall, looking at the sofa
        sides = {"x-": sx - min(xs), "x+": max(xs) - sx, "z-": sz - min(zs), "z+": max(zs) - sz}
        back = min(sides, key=sides.get)
        cx, cz = _clear_spot(back, sofa, xs, zs, room, placed)
        cam.location = (cx * IN, -cz * IN, eye)
        target.location = (sx * IN, -sz * IN, floor_z + 0.55)
        return True
    if name == "door":
        if not room["doors"]:
            return False
        d = room["doors"][0]
        (dx, dz), (nx, nz) = d["center"], d["into_room"]
        cam.location = ((dx + nx * 10) * IN, -(dz + nz * 10) * IN, eye)
        target.location = (centre.x, centre.y, floor_z + 0.6)
        return True
    return False


def render(path: str) -> None:
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    a = args()
    plan = json.loads(a["plan"].read_text())
    products = {p["id"]: p for p in json.loads((ROOT / "data/products.json").read_text())["products"]}
    models = json.loads((ROOT / "web/public/models/index.json").read_text())
    room = load_scan(a["scan"])
    placed = place(room, plan, products)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(a["scan"]))
    scan_objs = list(bpy.data.objects)
    floor = [o for o in scan_objs if o.name.startswith("Floor_") and o.type == "MESH"]
    lo, hi = bounds(floor or scan_objs)
    floor_z = hi.z if floor else lo.z
    cam, target = setup_scene(a["res"], lo, hi, floor_z)
    a["out"].parent.mkdir(parents=True, exist_ok=True)
    out = str(a["out"])
    written = []
    shot("overview", cam, target, lo, hi, floor_z, scan_objs, placed, room)
    render(out + "_before.png")
    written.append(out + "_before.png")
    for it in placed:
        add_model(it, floor_z, models)
    for name in a["shots"]:
        if shot(name, cam, target, lo, hi, floor_z, scan_objs, placed, room):
            path = out + ("_after.png" if name == "overview" else f"_{name}.png")
            render(path)
            written.append(path)
    Path(out + ".json").write_text(json.dumps(
        {"plan": str(a["plan"].relative_to(ROOT)), "scan": str(a["scan"].relative_to(ROOT)), "placed": placed,
         "shots": [Path(w).name for w in written]}, indent=1, ensure_ascii=False))
    print(f"render: {len(placed)} products placed -> " + ", ".join(Path(w).name for w in written))


main()
