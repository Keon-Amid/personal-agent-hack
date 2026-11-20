"""Render the scanned room with the agent's picks, headless in Blender (stills for the demo video).

    /Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/render_blender.py -- \
        [--plan contracts/plan.room_scan.json] [--scan assets/room_scan_roomplan.glb] [--out renders/room] [--res 1600x900]

Writes <out>_before.png (the room as scanned) and <out>_after.png (with the agent's products), plus <out>.json with
every placement. Positions are not invented: each product goes where fit.layout.find_spot says it fits (inside the
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
from fit.scan import load_scan  # noqa: E402

IN = 0.0254  # inches -> meters


def args() -> dict:
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    get = lambda f, d: a[a.index(f) + 1] if f in a else d  # noqa: E731
    w, h = get("--res", "1600x900").lower().split("x")
    return {"plan": ROOT / get("--plan", "contracts/plan.room_scan.json"),
            "scan": ROOT / get("--scan", "assets/room_scan_roomplan.glb"),
            "out": ROOT / get("--out", "renders/room"), "res": (int(w), int(h))}


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


def setup_scene(res: tuple[int, int], lo: Vector, hi: Vector):
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    world = bpy.data.worlds.new("w") if not sc.world else sc.world
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.92, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
    centre = (lo + hi) / 2
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.0
    sun.rotation_euler = (math.radians(40), 0, math.radians(30))
    sc.collection.objects.link(sun)
    area = bpy.data.objects.new("area", bpy.data.lights.new("area", "AREA"))
    area.data.energy, area.data.size = 250, 4
    area.location = (centre.x, centre.y, hi.z + 1.5)
    sc.collection.objects.link(area)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 22
    span = max(hi.x - lo.x, hi.y - lo.y)
    cam.location = (centre.x + span * 0.55, centre.y - span * 0.75, lo.z + span * 0.95)
    target = bpy.data.objects.new("target", None)
    target.location = (centre.x, centre.y, lo.z + 0.4)
    sc.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target, c.track_axis, c.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.collection.objects.link(cam)
    sc.camera = cam


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
    for o in scan_objs:  # no ceiling, so the camera can look in from above
        if o.name.startswith("Ceiling"):
            o.hide_render = True
    floor = [o for o in scan_objs if o.name.startswith("Floor_") and o.type == "MESH"]
    lo, hi = bounds(floor or scan_objs)
    floor_z = hi.z if floor else lo.z
    centre = (lo + hi) / 2
    for o in scan_objs:  # cut-away view: hide the walls between the camera (front-right) and the room
        if o.type == "MESH" and o.name.split("_")[0] in ("Wall", "Joint"):
            wl, wh = bounds([o])
            c = (wl + wh) / 2
            thin_y = (wh.y - wl.y) < (wh.x - wl.x)
            if (thin_y and c.y < centre.y) or (not thin_y and c.x > centre.x):
                o.hide_render = True
    setup_scene(a["res"], lo, hi)

    a["out"].parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(a["out"]) + "_before.png"
    bpy.ops.render.render(write_still=True)
    for it in placed:
        add_model(it, floor_z, models)
    bpy.context.scene.render.filepath = str(a["out"]) + "_after.png"
    bpy.ops.render.render(write_still=True)
    Path(str(a["out"]) + ".json").write_text(json.dumps(
        {"plan": str(a["plan"].relative_to(ROOT)), "scan": str(a["scan"].relative_to(ROOT)), "placed": placed},
        indent=1, ensure_ascii=False))
    print(f"render: {len(placed)} products placed -> {a['out']}_before.png, {a['out']}_after.png")


main()
