"""Room outline from a full-room LiDAR scan (iPhone/iPad Pro: 3D Scanner App, Polycam, RoomPlan, ARKit). Stdlib only.

scan(data, name) -> ScanResult dict: floor outline polygon (inches, walls axis-aligned, origin at a corner),
wall lengths, depth into the room from the longest wall, ceiling height, door openings, and fit.measurement values
for room(). to_measurements(result) maps it onto the 4 room keys.

Method (the standard plane-based floor-plan pipeline used by open-source scan-to-floorplan tools, e.g.
Open3D plane segmentation + occupancy-grid tracing, done here without numpy):
1. Parse the mesh (OBJ, or PLY ascii/binary; a point cloud also works). ARKit exports are metres, gravity-aligned.
2. Up axis = the axis with the most horizontal surface at one height (the floor). Floor height = peak of the
   area-weighted histogram of up-facing triangles; ceiling = the same peak 1.8 m+ above the floor, if scanned.
3. Wall points = vertical triangles sampled every 5 cm, 0.9 m above the floor up to the ceiling (above most
   furniture; the strip above a door closes its opening). Dominant wall direction = area-weighted histogram of wall
   normals modulo 90 degrees; rotate so walls are axis-aligned.
4. Rasterize at 5 cm, close gaps by dilation, flood-fill from outside, keep the largest enclosed region, undo the
   dilation, trace its boundary, drop jogs < 20 cm -> a rectilinear outline. Then each edge is snapped to the
   median of the wall points near it (sub-cm), and the spread of those points (MAD) sets the error.
5. Doors: along each wall, a gap in the wall surface both low (0.1-0.7 m) and mid (1.0-1.8 m) that is 0.6-1.3 m
   wide. A closed door is flush with the wall and is NOT found; then the person measures it.
Limits: rooms are assumed rectilinear (right-angle walls); a tall wardrobe against a wall reads as wall.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from collections import deque

M_TO_IN = 39.37007874
CELL = 0.05            # m, raster cell
SAMPLE = 0.05          # m, triangle sampling step
WALL_BAND_LO = 0.9     # m above floor
MIN_JOG = 0.20         # m, shorter outline edges are noise
SNAP_TOL = 0.20        # m, wall points this close to an edge refine it
MIN_ROOM_M2 = 2.0
DILATE_STEPS = (1, 2, 3, 4, 6, 8, 10, 12)
GOOD_DILATE = 8        # cells; closing more than 0.8 m of gap means the band was poorly scanned
HIGH_BAND_LO = 2.1     # m above floor: above standard doors (2.03 m) and most wardrobes
SCAN_MIN_ERR_IN = 1.0  # LiDAR room scans are good to about an inch at best
DOOR_MIN, DOOR_MAX, OPENING_MAX = 0.6, 1.3, 3.0  # m


class ScanError(ValueError):
    pass


# ---------------------------------------------------------------- parsing

def _parse_obj(text: str):
    verts, faces = [], []
    for line in text.splitlines():
        if line.startswith("v "):
            p = line.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
        elif line.startswith("f "):
            idx = []
            for tok in line.split()[1:]:
                i = int(tok.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            for k in range(1, len(idx) - 1):
                faces.append((idx[0], idx[k], idx[k + 1]))
    return verts, faces


_PLY_T = {"char": "b", "int8": "b", "uchar": "B", "uint8": "B", "short": "h", "int16": "h", "ushort": "H",
          "uint16": "H", "int": "i", "int32": "i", "uint": "I", "uint32": "I", "float": "f", "float32": "f",
          "double": "d", "float64": "d"}


def _parse_ply(data: bytes):
    end = data.find(b"end_header")
    if end < 0:
        raise ScanError("PLY without end_header")
    body = end + len(b"end_header")
    body += 2 if data[body:body + 2] == b"\r\n" else 1
    header = data[:end].decode("ascii", errors="replace").splitlines()
    fmt, elements = None, []
    for ln in header:
        p = ln.split()
        if not p:
            continue
        if p[0] == "format":
            fmt = p[1]
        elif p[0] == "element":
            elements.append({"name": p[1], "count": int(p[2]), "props": []})
        elif p[0] == "property" and elements:
            if p[1] == "list":
                elements[-1]["props"].append(("list", p[2], p[3], p[4]))
            else:
                elements[-1]["props"].append(("scalar", p[1], p[2]))
    verts, faces = [], []
    if fmt == "ascii":
        rows = iter(data[body:].decode("ascii", errors="replace").split("\n"))
        for el in elements:
            names = [pr[-1] for pr in el["props"]]
            for _ in range(el["count"]):
                vals = next(rows).split()
                if el["name"] == "vertex":
                    d = dict(zip(names, vals))
                    verts.append((float(d["x"]), float(d["y"]), float(d["z"])))
                elif el["name"] == "face":
                    n = int(vals[0])
                    idx = [int(v) for v in vals[1:1 + n]]
                    faces += [(idx[0], idx[k], idx[k + 1]) for k in range(1, n - 1)]
        return verts, faces
    if fmt not in ("binary_little_endian", "binary_big_endian"):
        raise ScanError(f"unsupported PLY format {fmt!r}")
    bo = "<" if fmt == "binary_little_endian" else ">"
    off = body
    for el in elements:
        props = el["props"]
        if all(pr[0] == "scalar" for pr in props):
            st = struct.Struct(bo + "".join(_PLY_T[pr[1]] for pr in props))
            names = [pr[2] for pr in props]
            n = el["count"]
            chunk = data[off:off + st.size * n]
            off += st.size * n
            if el["name"] == "vertex":
                ix, iy, iz = names.index("x"), names.index("y"), names.index("z")
                verts = [(r[ix], r[iy], r[iz]) for r in st.iter_unpack(chunk)]
            continue
        for _ in range(el["count"]):
            idx = None
            for pr in props:
                if pr[0] == "scalar":
                    off += struct.calcsize(_PLY_T[pr[1]])
                    continue
                (n,) = struct.unpack_from(bo + _PLY_T[pr[1]], data, off)
                off += struct.calcsize(_PLY_T[pr[1]])
                it = _PLY_T[pr[2]]
                vals = struct.unpack_from(bo + it * n, data, off)
                off += struct.calcsize(it) * n
                if pr[3] in ("vertex_indices", "vertex_index"):
                    idx = vals
            if el["name"] == "face" and idx:
                faces += [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]
    return verts, faces


_GLB_COMP = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}


def _mat_mul(a, b):
    return [sum(a[r + 4 * k] * b[k + 4 * c] for k in range(4)) for c in range(4) for r in range(4)]


def _node_matrix(n):
    """Column-major 4x4 for a glTF node (matrix, or T * R * S)."""
    if "matrix" in n:
        return list(n["matrix"])
    tx, ty, tz = n.get("translation", (0, 0, 0))
    x, y, z, w = n.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = n.get("scale", (1, 1, 1))
    r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
         2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
         2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0,
         0, 0, 0, 1]
    s = [sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, sz, 0, 0, 0, 0, 1]
    t = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, tx, ty, tz, 1]
    return _mat_mul(t, _mat_mul(r, s))


def _parse_glb(data: bytes) -> tuple[list, list]:
    """Binary glTF 2.0 (e.g. an iPhone LiDAR export): every triangle primitive, world transforms applied.
    Uncompressed only: Draco / meshopt compressed files raise ScanError."""
    _, version, _ = struct.unpack_from("<4sII", data, 0)
    if version != 2:
        raise ScanError(f"GLB version {version}; only glTF 2.0 is supported")
    off, js, binc = 12, None, b""
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<I4s", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(chunk)
        elif ctype == b"BIN\x00":
            binc = chunk
        off += 8 + clen
    if js is None:
        raise ScanError("GLB has no JSON chunk")
    used = set(js.get("extensionsRequired", [])) | set(js.get("extensionsUsed", []))
    if used & {"KHR_draco_mesh_compression", "EXT_meshopt_compression"}:
        raise ScanError(f"GLB is compressed ({sorted(used)}); re-export it uncompressed, or as OBJ/PLY")

    def read(ai):
        a = js["accessors"][ai]
        bv = js["bufferViews"][a["bufferView"]]
        fmt = _GLB_COMP[a["componentType"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        size = struct.calcsize("<" + fmt)
        stride = bv.get("byteStride") or size * n
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from("<" + fmt * n, binc, base + i * stride) for i in range(a["count"])]

    verts, faces = [], []

    def walk(ni, parent):
        node = js["nodes"][ni]
        m = _mat_mul(parent, _node_matrix(node))
        if "mesh" in node:
            for prim in js["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                base = len(verts)
                for x, y, z in read(prim["attributes"]["POSITION"]):
                    verts.append((m[0] * x + m[4] * y + m[8] * z + m[12],
                                  m[1] * x + m[5] * y + m[9] * z + m[13],
                                  m[2] * x + m[6] * y + m[10] * z + m[14]))
                idx = [i[0] for i in read(prim["indices"])] if "indices" in prim else list(range(len(verts) - base))
                faces.extend((base + idx[k], base + idx[k + 1], base + idx[k + 2]) for k in range(0, len(idx) - 2, 3))
        for c in node.get("children", []):
            walk(c, m)

    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    scene = js["scenes"][js.get("scene", 0)] if js.get("scenes") else {"nodes": list(range(len(js.get("nodes", []))))}
    for ni in scene["nodes"]:
        walk(ni, ident)
    return verts, faces


def load_mesh(data: bytes, name: str = "") -> tuple[list, list]:
    """(vertices [(x, y, z)], triangles [(i, j, k)]) from OBJ or PLY bytes. Triangles may be empty (point cloud)."""
    if data[:3] == b"ply":
        verts, faces = _parse_ply(data)
    elif data[:4] == b"glTF":
        verts, faces = _parse_glb(data)
    elif name.lower().endswith((".usdz", ".usd", ".usdc", ".gltf")):
        raise ScanError(f"{name}: export the scan as GLB, OBJ or PLY (USDZ and text glTF aren't readable here)")
    else:
        verts, faces = _parse_obj(data.decode("utf-8", errors="replace"))
    if len(verts) < 100:
        raise ScanError(f"scan has only {len(verts)} vertices; is this a room scan?")
    return verts, faces


# ---------------------------------------------------------------- geometry helpers

def _tri_info(verts, faces):
    """Per triangle: (unit normal, area, centroid, (a, b, c))."""
    out = []
    for i, j, k in faces:
        a, b, c = verts[i], verts[j], verts[k]
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        L = math.sqrt(nx * nx + ny * ny + nz * nz)
        if L == 0:
            continue
        out.append(((nx / L, ny / L, nz / L), L / 2,
                    ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3), (a, b, c)))
    return out


def _peak(values, weights, lo, hi, step=0.02):
    """Centre of the heaviest bin of values in [lo, hi] (weights summed). (centre, weight) or (None, 0)."""
    if hi <= lo:
        return None, 0.0
    n = int((hi - lo) / step) + 1
    bins = [0.0] * n
    for v, w in zip(values, weights):
        if lo <= v <= hi:
            bins[int((v - lo) / step)] += w
    sm = [sum(bins[max(0, i - 1):i + 2]) for i in range(n)]
    i = max(range(n), key=sm.__getitem__)
    if sm[i] == 0:
        return None, 0.0
    # weighted mean inside the 3-bin window for sub-bin precision
    num = den = 0.0
    for v, w in zip(values, weights):
        if lo + (i - 1) * step <= v < lo + (i + 2) * step:
            num += v * w
            den += w
    return num / den, sm[i]


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _sample_tri(a, b, c, step):
    """Points on triangle abc about `step` apart (just the centroid for small triangles)."""
    e = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
    if e <= step:
        return [((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)]
    n = math.ceil(e / step)
    pts = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            u, v = i / n, j / n
            w = 1 - u - v
            pts.append((w * a[0] + u * b[0] + v * c[0], w * a[1] + u * b[1] + v * c[1], w * a[2] + u * b[2] + v * c[2]))
    return pts


def _dilate(grid, nx, ny, r):
    """Square dilation of a bytearray grid (index i + j*nx) by r cells, separable, O(cells)."""
    if r <= 0:
        return bytearray(grid)
    tmp = bytearray(nx * ny)
    for j in range(ny):
        row = j * nx
        pre = [0] * (nx + 1)
        for i in range(nx):
            pre[i + 1] = pre[i] + grid[row + i]
        for i in range(nx):
            if pre[min(nx, i + r + 1)] - pre[max(0, i - r)]:
                tmp[row + i] = 1
    out = bytearray(nx * ny)
    for i in range(nx):
        pre = [0] * (ny + 1)
        for j in range(ny):
            pre[j + 1] = pre[j] + tmp[i + j * nx]
        for j in range(ny):
            if pre[min(ny, j + r + 1)] - pre[max(0, j - r)]:
                out[i + j * nx] = 1
    return out


def _components(mask, nx, ny):
    """Largest 4-connected component of mask (bytearray) -> bytearray."""
    seen = bytearray(nx * ny)
    best = []
    for s in range(nx * ny):
        if not mask[s] or seen[s]:
            continue
        comp, q = [], deque([s])
        seen[s] = 1
        while q:
            c = q.popleft()
            comp.append(c)
            i, j = c % nx, c // nx
            for d, ok in ((c - 1, i > 0), (c + 1, i < nx - 1), (c - nx, j > 0), (c + nx, j < ny - 1)):
                if ok and mask[d] and not seen[d]:
                    seen[d] = 1
                    q.append(d)
        if len(comp) > len(best):
            best = comp
    out = bytearray(nx * ny)
    for c in best:
        out[c] = 1
    return out


def _trace(mask, nx, ny):
    """Boundary loop (grid corner coords, CCW) of the largest region in mask."""
    nxt = {}
    for c in range(nx * ny):
        if not mask[c]:
            continue
        i, j = c % nx, c // nx
        if j == 0 or not mask[c - nx]:
            nxt.setdefault((i, j), []).append((i + 1, j))
        if i == nx - 1 or not mask[c + 1]:
            nxt.setdefault((i + 1, j), []).append((i + 1, j + 1))
        if j == ny - 1 or not mask[c + nx]:
            nxt.setdefault((i + 1, j + 1), []).append((i, j + 1))
        if i == 0 or not mask[c - 1]:
            nxt.setdefault((i, j + 1), []).append((i, j))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop, p = [start], start
        while True:
            outs = nxt.get(p)
            if not outs:
                break
            q = outs.pop()
            if not outs:
                del nxt[p]
            if q == start:
                break
            loop.append(q)
            p = q
        loops.append(loop)
    return max(loops, key=lambda L: abs(_area(L)))


def _area(poly):
    return sum(poly[k][0] * poly[(k + 1) % len(poly)][1] - poly[(k + 1) % len(poly)][0] * poly[k][1]
               for k in range(len(poly))) / 2


def _clean(poly, eps=1e-9):
    """Drop repeated and collinear vertices of a rectilinear polygon."""
    changed = True
    while changed and len(poly) > 4:
        changed = False
        out = []
        n = len(poly)
        for k in range(n):
            a, b, c = poly[k - 1], poly[k], poly[(k + 1) % n]
            if math.dist(a, b) < eps:
                changed = True
                continue
            if (abs(a[0] - b[0]) < eps and abs(b[0] - c[0]) < eps) or (abs(a[1] - b[1]) < eps and abs(b[1] - c[1]) < eps):
                changed = True
                continue
            out.append(b)
        poly = out
    return poly


def _drop_jogs(poly, min_len):
    """Remove rectilinear edges shorter than min_len by snapping the shorter neighbour onto the longer one's line."""
    poly = [list(p) for p in _clean(poly)]
    for _ in range(500):
        n = len(poly)
        if n <= 4:
            break
        lens = [math.dist(poly[k], poly[(k + 1) % n]) for k in range(n)]
        k = min(range(n), key=lens.__getitem__)
        if lens[k] >= min_len:
            break
        prv, nxt = (k - 1) % n, (k + 1) % n
        horiz = abs(poly[k][1] - poly[(k + 1) % n][1]) < 1e-9  # short edge horizontal -> neighbours vertical
        ax = 0 if horiz else 1  # coordinate the neighbours share along their line
        if lens[prv] >= lens[nxt]:
            val = poly[k][ax]
            poly[(k + 1) % n][ax] = val
            poly[(k + 2) % n][ax] = val
        else:
            val = poly[(k + 1) % n][ax]
            poly[k][ax] = val
            poly[(k - 1) % n][ax] = val
        poly = [list(p) for p in _clean([tuple(p) for p in poly])]
    return [tuple(p) for p in poly]


# ---------------------------------------------------------------- the pipeline

def _choose_up(verts, tris):
    """Index of the gravity axis: most horizontal-surface weight concentrated at one height near the bottom."""
    scores = []
    for ax in range(3):
        hs = [v[ax] for v in verts]
        lo, hi = min(hs), max(hs)
        if tris:
            vals = [t[2][ax] for t in tris if abs(t[0][ax]) > 0.9]
            ws = [t[1] for t in tris if abs(t[0][ax]) > 0.9]
        else:
            vals, ws = hs, [1.0] * len(hs)
        _, w = _peak(vals, ws, lo, lo + 0.3 * (hi - lo), 0.03)
        scores.append(w)
    best = max(range(3), key=scores.__getitem__)
    # ARKit is y-up: keep y unless another axis is clearly stronger
    if best != 1 and scores[best] < 1.3 * scores[1]:
        best = 1
    return best, scores


def _units(verts):
    ext = max(max(v[a] for v in verts) - min(v[a] for v in verts) for a in range(3))
    if ext > 3000:  # a room is < 30 m across: bigger numbers are cm, then mm
        return 0.001, "mm"
    if ext > 30:
        return 0.01, "cm"
    return 1.0, "m"


def scan(data: bytes, name: str = "scan.obj", up: str = "auto") -> dict:
    """Full room scan -> outline + measurements. Raises ScanError with a plain reason."""
    verts, faces = load_mesh(data, name)
    scale, unit = _units(verts)
    if scale != 1.0:
        verts = [(x * scale, y * scale, z * scale) for x, y, z in verts]
    tris = _tri_info(verts, faces) if faces else []
    if up == "auto":
        ui, up_scores = _choose_up(verts, tris)
    else:
        ui, up_scores = "xyz".index(up), None
    a1, a2 = [a for a in range(3) if a != ui]

    # floor + ceiling
    hs = [v[ui] for v in verts]
    hmin, hmax = min(hs), max(hs)
    if tris:
        horiz = [t for t in tris if abs(t[0][ui]) > 0.9]
        hv, hw = [t[2][ui] for t in horiz], [t[1] for t in horiz]
    else:
        hv, hw = hs, [1.0] * len(hs)
    floor, fw = _peak(hv, hw, hmin, hmin + 0.5 * (hmax - hmin))
    if floor is None:
        raise ScanError("no floor found in the scan (no large flat surface at the bottom)")
    ceil, cw = _peak(hv, hw, floor + 1.8, hmax)
    if ceil is not None and cw < 0.2 * fw:
        ceil = None
    top = ceil if ceil is not None else hmax
    if top - floor < 1.2:
        raise ScanError(f"scan is only {top - floor:.2f} m tall above the floor; scan the walls up to the ceiling")

    # wall points (and door-band points) as (u, v, h)
    wall_pts, door_pts, wall_normals = [], [], []
    if tris:
        for n, area, cen, (a, b, c) in tris:
            if abs(n[ui]) > 0.3 or cen[ui] < floor + 0.05 or cen[ui] > top - 0.03:
                continue
            wall_normals.append((n[a1], n[a2], area))
            for p in _sample_tri(a, b, c, SAMPLE):
                h = p[ui] - floor
                q = (p[a1], p[a2], h)
                door_pts.append(q)
    else:
        for p in verts:
            h = p[ui] - floor
            if 0.05 <= h <= top - floor - 0.03:
                q = (p[a1], p[a2], h)
                door_pts.append(q)
    wall_pts = [q for q in door_pts if WALL_BAND_LO <= q[2] <= top - floor - 0.08]
    if len(wall_pts) < 50:
        raise ScanError("too few wall points above furniture height; scan the walls up to the ceiling")

    # dominant wall direction
    if wall_normals:
        bins = [0.0] * 180  # 0.5 degree bins over [0, 90)
        for nu, nv, w in wall_normals:
            L = math.hypot(nu, nv)
            if L < 0.5:
                continue
            ang = math.degrees(math.atan2(nv, nu)) % 90
            bins[int(ang * 2) % 180] += w * L
        sm = [sum(bins[(i + d) % 180] for d in range(-3, 4)) for i in range(180)]
        pk = max(range(180), key=sm.__getitem__) / 2
        # circular weighted mean within +-3 deg of the peak
        sx = sy = 0.0
        for nu, nv, w in wall_normals:
            ang = math.degrees(math.atan2(nv, nu)) % 90
            dd = (ang - pk + 45) % 90 - 45
            if abs(dd) <= 3:
                sx += w * math.cos(math.radians(ang * 4))
                sy += w * math.sin(math.radians(ang * 4))
        theta = math.degrees(math.atan2(sy, sx)) / 4 % 90 if (sx or sy) else pk
    else:
        sub = wall_pts[:: max(1, len(wall_pts) // 4000)]

        def bbox_area(t):
            ct, st = math.cos(math.radians(t)), math.sin(math.radians(t))
            xs = [p[0] * ct + p[1] * st for p in sub]
            ys = [-p[0] * st + p[1] * ct for p in sub]
            return (max(xs) - min(xs)) * (max(ys) - min(ys))
        theta = min((t / 2 for t in range(180)), key=bbox_area)
        theta = min((theta + d / 10 for d in range(-10, 11)), key=bbox_area)
    ct, st = math.cos(math.radians(theta)), math.sin(math.radians(theta))

    def rot(p):
        return (p[0] * ct + p[1] * st, -p[0] * st + p[1] * ct, p[2])
    D = [rot(p) for p in door_pts]
    H = top - floor
    bands = [(WALL_BAND_LO, H - 0.08)]
    if ceil is not None and H - 0.08 - max(WALL_BAND_LO, min(HIGH_BAND_LO, H - 0.35)) >= 0.15:
        # the strip under the ceiling: above wardrobes, shelves and door headers, so it shows the bare walls
        bands.insert(0, (max(WALL_BAND_LO, min(HIGH_BAND_LO, H - 0.35)), H - 0.08))
    tried, best = [], None
    for lo_h, hi_h in bands:
        W = [p for p in D if lo_h <= p[2] <= hi_h]
        if len(W) < 50:
            tried.append(f"{lo_h:.2f}-{hi_h:.2f} m: {len(W)} points")
            continue
        try:
            poly, r = _outline(W)
        except ScanError as e:
            tried.append(f"{lo_h:.2f}-{hi_h:.2f} m: {e}")
            continue
        if best is None or r < best[2]:
            best = (W, poly, r, (round(lo_h, 2), round(hi_h, 2)))
        if r <= GOOD_DILATE:
            break
    if best is None:
        raise ScanError("couldn't find a closed room outline (" + "; ".join(tried) + "). Rescan, covering every "
                        "wall up to the ceiling")
    W, poly, r_used, band = best

    # snap each edge to the median of nearby wall points; collect spread
    n = len(poly)
    lines, mads = [], []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        horiz = abs(a[1] - b[1]) < 1e-9
        ax, along = (1, 0) if horiz else (0, 1)
        c = a[ax]
        lo, hi = sorted((a[along], b[along]))
        near = [p[ax] for p in W if lo + 0.1 <= p[along] <= hi - 0.1 and abs(p[ax] - c) < SNAP_TOL]
        if len(near) >= 10:
            c = _median(near)
            mads.append(_median([abs(v - c) for v in near]))
        lines.append((ax, c))
    for k in range(n):
        if lines[k][0] == lines[k - 1][0]:
            raise ScanError("outline edges don't alternate; scan is too noisy to trace")
    poly = []
    for k in range(n):
        p = [0.0, 0.0]
        for ax, c in (lines[k - 1], lines[k]):
            p[ax] = c
        poly.append(tuple(p))

    ox, oy = min(p[0] for p in poly), min(p[1] for p in poly)
    mad = _median(mads) if mads else 0.02
    err_in = round(max(SCAN_MIN_ERR_IN, 2 * mad * M_TO_IN), 1)

    walls_out = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        walls_out.append({"id": f"w{k + 1}", "from_in": _xy_in(a, ox, oy), "to_in": _xy_in(b, ox, oy),
                          "length_in": round(math.dist(a, b) * M_TO_IN, 1)})
    longest = max(range(n), key=lambda k: math.dist(poly[k], poly[(k + 1) % n]))
    depth_m = _depth_from(poly, longest)

    doors = _find_doors(poly, D, ox, oy)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    result = {
        "outline_in": [_xy_in(p, ox, oy) for p in poly],
        "walls": walls_out,
        "longest_wall": walls_out[longest]["id"],
        "width_in": round((max(xs) - min(xs)) * M_TO_IN, 1),
        "length_in": round((max(ys) - min(ys)) * M_TO_IN, 1),
        "depth_in": round(depth_m * M_TO_IN, 1),
        "area_sqft": round(abs(_area(poly)) * 10.7639, 1),
        "ceiling_in": round((ceil - floor) * M_TO_IN, 1) if ceil is not None else None,
        "doors": doors,
        "error_in": err_in,
        "method": {"up_axis": "xyz"[ui], "up_scores": [round(s, 2) for s in up_scores] if up_scores else None,
                   "units": unit, "vertices": len(verts), "triangles": len(faces),
                   "wall_points": len(W), "rotation_deg": round(theta, 2),
                   "origin_m": [round(ox, 4), round(oy, 4)], "floor_m": round(floor, 4), "gap_closing_m": round(2 * r_used * CELL, 2),
                   "wall_band_m": list(band),
                   "edge_spread_mad_in": round(mad * M_TO_IN, 2), "file": name},
    }
    return result


def _outline(W):
    """Wall points (u, v, h) in the wall-aligned frame -> (rectilinear CCW polygon in m, dilation cells used)."""
    pad = DILATE_STEPS[-1] + 3
    xmin = min(p[0] for p in W) - pad * CELL
    ymin = min(p[1] for p in W) - pad * CELL
    nx = int((max(p[0] for p in W) - xmin) / CELL) + pad + 1
    ny = int((max(p[1] for p in W) - ymin) / CELL) + pad + 1
    occ = bytearray(nx * ny)
    for x, y, _ in W:
        occ[int((x - xmin) / CELL) + int((y - ymin) / CELL) * nx] = 1
    for r in DILATE_STEPS:
        walls = _dilate(occ, nx, ny, r)
        outside = bytearray(nx * ny)
        q = deque(c for c in range(nx * ny) if (c % nx in (0, nx - 1) or c // nx in (0, ny - 1)) and not walls[c])
        for c in q:
            outside[c] = 1
        while q:
            c = q.popleft()
            i, j = c % nx, c // nx
            for d, ok in ((c - 1, i > 0), (c + 1, i < nx - 1), (c - nx, j > 0), (c + nx, j < ny - 1)):
                if ok and not walls[d] and not outside[d]:
                    outside[d] = 1
                    q.append(d)
        free = _components(bytearray(1 if not walls[c] and not outside[c] else 0 for c in range(nx * ny)), nx, ny)
        if sum(free) * CELL * CELL < MIN_ROOM_M2:
            continue
        grown = _dilate(free, nx, ny, r)
        region = _components(bytearray(1 if grown[c] and not outside[c] else 0 for c in range(nx * ny)), nx, ny)
        poly = [(xmin + i * CELL, ymin + j * CELL) for i, j in _trace(region, nx, ny)]
        if _area(poly) < 0:
            poly.reverse()
        poly = _drop_jogs(poly, MIN_JOG)
        if len(poly) < 4:
            raise ScanError("outline collapsed; the scan is too sparse")
        return poly, r
    raise ScanError(f"walls have gaps wider than {2 * DILATE_STEPS[-1] * CELL:.1f} m")


def _xy_in(p, ox, oy):
    return [round((p[0] - ox) * M_TO_IN, 1), round((p[1] - oy) * M_TO_IN, 1)]


def _depth_from(poly, k):
    """Distance from the midpoint of edge k straight into the room to the nearest parallel edge (CCW polygon)."""
    n = len(poly)
    a, b = poly[k], poly[(k + 1) % n]
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    ix, iy = -dy / L, dx / L  # left normal = interior for CCW
    best = math.inf
    for j in range(n):
        if j == k:
            continue
        p, q = poly[j], poly[(j + 1) % n]
        if abs(ix) > 0.5 and abs(p[0] - q[0]) < 1e-9 and min(p[1], q[1]) <= my <= max(p[1], q[1]):
            t = (p[0] - mx) / ix
        elif abs(iy) > 0.5 and abs(p[1] - q[1]) < 1e-9 and min(p[0], q[0]) <= mx <= max(p[0], q[0]):
            t = (p[1] - my) / iy
        else:
            continue
        if t > 1e-6:
            best = min(best, t)
    return best if best < math.inf else 0.0


def _find_doors(poly, pts, ox, oy, tol=0.12, step=0.05):
    """Openings in the wall surface along each edge: empty both low and mid. Door if 0.6-1.3 m wide."""
    n = len(poly)
    out = []
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        horiz = abs(a[1] - b[1]) < 1e-9
        ax, along = (1, 0) if horiz else (0, 1)
        lo, hi = sorted((a[along], b[along]))
        nb = int((hi - lo) / step)
        if nb < 4:
            continue
        low, mid, top_h = bytearray(nb), bytearray(nb), [math.inf] * nb
        for p in pts:
            if abs(p[ax] - a[ax]) > tol or not lo <= p[along] < hi:
                continue
            i = min(nb - 1, int((p[along] - lo) / step))
            h = p[2]
            if 0.1 <= h <= 0.7:
                low[i] = 1
            elif 1.0 <= h <= 1.8:
                mid[i] = 1
            elif h > 1.8:
                top_h[i] = min(top_h[i], h)
        i = 1
        while i < nb - 1:
            if low[i] or mid[i]:
                i += 1
                continue
            j = i
            while j < nb - 1 and not low[j] and not mid[j]:
                j += 1
            w = (j - i) * step
            if DOOR_MIN <= w <= OPENING_MAX:
                heads = sorted(t for t in top_h[i:j] if t < math.inf)
                start = lo + i * step
                pa = [0.0, 0.0]
                pa[ax], pa[along] = a[ax], start
                out.append({"wall": f"w{k + 1}", "kind": "door" if w <= DOOR_MAX else "opening",
                            "width_in": round(w * M_TO_IN, 1),
                            "height_in": round(_median(heads) * M_TO_IN, 1) if len(heads) >= 3 else None,
                            "at_in": _xy_in(pa, ox, oy)})
            i = j
    return out


def to_measurements(res: dict, wall_id: str | None = None) -> dict:
    """{key: fit.measurement} for the keys the scan measured (wall, depth, and door_width/height if a door was found).
    wall_id picks the wall section the furniture goes against (e.g. "w7"); default is the longest wall."""
    from fit.checks import measurement
    e = res["error_in"]
    wid = wall_id or res["longest_wall"]
    chosen = next((w for w in res["walls"] if w["id"] == wid), None)
    if chosen is None:
        raise ScanError(f"no wall {wid!r} in the scan; walls are " + ", ".join(
            f'{w["id"]} {w["length_in"]:g} in' for w in res["walls"]))
    m = {"wall": measurement(chosen["length_in"], e, "scanned:lidar"),
         "depth": measurement(res["depth_in"], e, "scanned:lidar")}
    doors = sorted((d for d in res["doors"] if d["kind"] == "door"), key=lambda d: d["width_in"])
    if doors:
        d = doors[0]  # the narrowest door is the one furniture must get through
        m["door_width"] = measurement(d["width_in"], max(e, 2.0), "scanned:lidar")  # 5 cm gap bins
        if d["height_in"]:
            m["door_height"] = measurement(d["height_in"], max(e, 2.0), "scanned:lidar")
    return m


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Room outline from a LiDAR scan (OBJ/PLY)")
    ap.add_argument("path")
    ap.add_argument("--up", default="auto", choices=["auto", "x", "y", "z"])
    ap.add_argument("--svg", help="write the outline as an SVG here")
    args = ap.parse_args()
    with open(args.path, "rb") as f:
        res = scan(f.read(), args.path, args.up)
    if args.svg:
        pts = res["outline_in"]
        W_, H_ = max(p[0] for p in pts) + 20, max(p[1] for p in pts) + 20
        path = " ".join(f"{p[0] + 10},{H_ - p[1] - 10}" for p in pts)
        labels = "".join(
            f'<text x="{(w["from_in"][0] + w["to_in"][0]) / 2 + 10}" y="{H_ - (w["from_in"][1] + w["to_in"][1]) / 2 - 10}"'
            f' font-size="8" text-anchor="middle">{w["length_in"]:g} in</text>' for w in res["walls"])
        with open(args.svg, "w") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_} {H_}" width="{W_ * 3}">'
                    f'<polygon points="{path}" fill="#eef" stroke="#226" stroke-width="1.5"/>{labels}</svg>')
    json.dump(res, sys.stdout, indent=1)
    print()
