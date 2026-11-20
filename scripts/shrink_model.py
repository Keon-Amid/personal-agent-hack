"""Shrink a generated .glb so it is small enough for the repo and fast in the browser.

Run by Blender, not by plain Python (scripts/make_model.py does this for you):
  blender -b --factory-startup -P scripts/shrink_model.py -- in.glb out.glb [max_triangles] [texture_px]

It cuts the triangle count with a Decimate modifier, scales textures down, and re-exports with JPEG textures.
The shape's proportions are not changed.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
max_tris = int(argv[2]) if len(argv) > 2 else 20000
tex_px = int(argv[3]) if len(argv) > 3 else 1024

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]


def triangles() -> int:
    return sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)


before = triangles()
ratio = min(1.0, max_tris / max(before, 1))
if ratio < 1.0:
    for o in meshes:
        bpy.context.view_layer.objects.active = o
        mod = o.modifiers.new("shrink", "DECIMATE")
        mod.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)

for img in bpy.data.images:
    w, h = img.size
    if w > tex_px or h > tex_px:
        scale = tex_px / max(w, h)
        img.scale(max(1, int(w * scale)), max(1, int(h * scale)))

props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
kw = {"filepath": out, "export_format": "GLB"}
if "export_image_format" in props:
    kw["export_image_format"] = "JPEG"
for name in ("export_image_quality", "export_jpeg_quality"):
    if name in props:
        kw[name] = 80
if "export_apply" in props:
    kw["export_apply"] = True
bpy.ops.export_scene.gltf(**kw)
print(f"SHRUNK {os.path.basename(out)}: {before} -> {triangles()} triangles, "
      f"{os.path.getsize(src) / 1e6:.1f} MB -> {os.path.getsize(out) / 1e6:.2f} MB")
