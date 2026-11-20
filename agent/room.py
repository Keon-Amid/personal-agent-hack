"""Room measurements from a photo (Superlinked object detection) and/or exact numbers the person typed.

estimate(photo_bytes=None, exact=None) -> (room, audit_records), room = fit.options.room(...).

Scale: a US interior door is 80 in tall, so inches_per_px = 80 / door box height in pixels. Wall width and
door width are box widths times that scale, with at least 10% error (20% if the door box touches the top or
bottom of the photo, i.e. the door may be cut off). Depth is not visible in a photo: give it in `exact`, or
we use an explicit rough default of 144 in with 25% error and say so in the audit.

Request/response shape is from Superlinked's docs (/docs/reference/api, /docs/extract/vision):
POST /v1/extract/{model} {"items": [image], "params": {"labels": [...]}} ->
{"items": [{"objects": [{"label", "score", "bbox": [x, y, w, h] px}]}]}.
NOT yet verified by a live call (SIE_API_KEY was empty when this was written).
"""
from __future__ import annotations

import json
import struct
import urllib.error
import urllib.parse
import urllib.request

from agent.types import audit
from fit.checks import measurement
from fit.options import room as make_room

KEYS = ("wall", "depth", "door_width", "door_height")
MODELS = ("IDEA-Research/grounding-dino-base", "google/owlv2-base-patch16-ensemble")
LABELS = ["door", "wall", "floor"]
DOOR_HEIGHT_IN = 80.0       # standard US interior door
DOOR_HEIGHT_ERR_IN = 2.0    # some older doors are 78 in
MIN_ERR = 0.10              # door-scale estimates are at least 10% off
CUT_OFF_ERR = 0.20          # door box touches the top or bottom edge: may be cut off
UNKNOWN_DIMS_ERR = 0.15     # couldn't read the image size, so couldn't check for cut-off
NO_WALL_ERR = 0.25          # no wall box: use the full photo width at the door's scale
DEFAULT_DEPTH_IN = 144.0
DEFAULT_DEPTH_ERR = 0.25
EDGE_PX = 3


class DetectionError(RuntimeError):
    pass


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) in px for PNG or JPEG, else None. Stdlib only."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg_len
    return None


def _fmt(data: bytes) -> str:
    return "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg"


def detect(photo: bytes, model: str) -> list[dict]:
    """POST /v1/extract/{model}; returns the objects list for the one image. Raises DetectionError."""
    from data import sie  # key loading + request style shared with the style step
    try:
        key = sie._key()
    except SystemExit as e:  # sie._key exits when the key is missing
        raise DetectionError(str(e)) from None
    url = f"{sie.API}/v1/extract/{urllib.parse.quote(model, safe='')}"
    body = json.dumps({"items": [sie.image_item(photo, _fmt(photo))], "params": {"labels": LABELS}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": sie.UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise DetectionError(f"{model}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise DetectionError(f"{model}: {e!r}") from None
    items = out.get("items") or []
    if not items:
        raise DetectionError(f"{model}: response has no items: {str(out)[:300]}")
    if items[0].get("error"):
        raise DetectionError(f"{model}: {items[0]['error']}")
    objs = items[0].get("objects")
    if objs is None:  # tolerate entities-with-bbox, which the API reference also describes
        objs = [e for e in items[0].get("entities") or [] if e.get("bbox")]
    return objs


def _box(obj: dict, size: tuple[int, int] | None) -> tuple[float, float, float, float, str]:
    """(x, y, w, h, format_used). Docs say [x, y, w, h]; if that overruns the image, it was [x1, y1, x2, y2]."""
    x, y, a, b = (float(v) for v in obj["bbox"])
    if size and (x + a > size[0] * 1.02 or y + b > size[1] * 1.02) and a > x and b > y:
        return x, y, a - x, b - y, "xyxy"
    return x, y, a, b, "xywh"


def _best(objs: list[dict], label: str) -> dict | None:
    hits = [o for o in objs if label in str(o.get("label", "")).lower() and o.get("bbox")]
    return max(hits, key=lambda o: o.get("score") or 0) if hits else None


def _from_photo(photo: bytes) -> tuple[dict, dict, str]:
    """Detect a door, return ({key: measurement}, source, why). Raises DetectionError."""
    errors, objs, model = [], None, None
    for m in MODELS:
        try:
            objs, model = detect(photo, m), m
            break
        except DetectionError as e:
            errors.append(str(e))
    if objs is None:
        raise DetectionError("; ".join(errors))
    size = image_size(photo)
    door = _best(objs, "door")
    if door is None:
        raise DetectionError(f"{model} found no door in the photo (labels seen: "
                             f"{sorted({str(o.get('label')) for o in objs}) or 'none'})")
    dx, dy, dw, dh, bfmt = _box(door, size)
    if dh <= 0 or dw <= 0:
        raise DetectionError(f"{model}: bad door box {door['bbox']}")
    ipp = DOOR_HEIGHT_IN / dh
    notes = []
    if size is None:
        err, cut = UNKNOWN_DIMS_ERR, None
        notes.append(f"couldn't read the photo size, so error is {UNKNOWN_DIMS_ERR:.0%}")
    else:
        cut = dy <= EDGE_PX or dy + dh >= size[1] - EDGE_PX
        err = CUT_OFF_ERR if cut else MIN_ERR
        if cut:
            notes.append(f"the door touches the photo edge and may be cut off, so error is {CUT_OFF_ERR:.0%}")
    est = {
        "door_height": measurement(DOOR_HEIGHT_IN, DOOR_HEIGHT_ERR_IN, "estimated:door"),
        "door_width": measurement(round(dw * ipp, 1), round(dw * ipp * err, 1), "estimated:door"),
    }
    wall = _best(objs, "wall")
    if wall is not None:
        _, _, ww, _, _ = _box(wall, size)
        est["wall"] = measurement(round(ww * ipp, 1), round(ww * ipp * err, 1), "estimated:door")
        wall_box = [round(v, 1) for v in _box(wall, size)[:4]]
    elif size is not None:
        est["wall"] = measurement(round(size[0] * ipp, 1), round(size[0] * ipp * NO_WALL_ERR, 1),
                                  "estimated:door")
        wall_box = None
        notes.append(f"no wall box found: wall = full photo width at the door's scale, error {NO_WALL_ERR:.0%}")
    else:
        wall_box = None
        notes.append("no wall box and no photo size: wall must be measured")
    source = {"kind": "superlinked", "model": model,
              "door_box": [round(v, 1) for v in (dx, dy, dw, dh)], "inches_per_px": round(ipp, 4),
              "bbox_format": bfmt, "door_score": door.get("score"), "wall_box": wall_box,
              "image_px": list(size) if size else None, "door_cut_off": cut}
    why = (f"door box is {dh:g} px tall; a US interior door is {DOOR_HEIGHT_IN:g} in, so 1 px = {ipp:.3f} in. "
           + " ".join(notes))
    return est, source, why.strip()


def estimate(photo_bytes: bytes | None = None, exact: dict | None = None, scan_bytes: bytes | None = None,
             scan_name: str = "scan.obj", scan_wall: str | None = None) -> tuple[dict, list[dict]]:
    """Room measurements -> (fit.options.room(...), [AuditRecord]).

    exact: {"wall", "depth", "door_width", "door_height"} in inches, typed by the person; each becomes
        fit.measurement(v, 0, "user") and overrides the photo estimate for that key.
    scan_bytes: a full-room LiDAR scan (OBJ/PLY, see agent.room_scan). It measures wall, depth and, if a door is
        open in the scan, door_width/door_height (source "scanned:lidar"); the photo only fills what's left.
    Precedence per key: exact > scan > photo > default.
    Raises ValueError naming what's missing when there's no photo and not all four exact values, or when the
    photo can't be read (with the Superlinked error) and exact values don't cover the gap.
    """
    exact = {k: v for k, v in (exact or {}).items() if v is not None}
    unknown = set(exact) - set(KEYS)
    if unknown:
        raise ValueError(f"unknown measurement keys: {sorted(unknown)} (use {list(KEYS)})")
    m = {k: measurement(float(exact[k]), 0.0, "user") for k in KEYS if k in exact}
    missing = [k for k in KEYS if k not in m]
    records = []

    if missing and scan_bytes is not None:
        from agent import room_scan
        try:
            res = room_scan.scan(scan_bytes, scan_name)
        except room_scan.ScanError as e:
            raise ValueError(f"couldn't read the room scan ({e})") from None
        try:
            scanned = room_scan.to_measurements(res, scan_wall)
        except room_scan.ScanError as e:
            raise ValueError(str(e)) from None
        got = {k: v for k, v in scanned.items() if k in missing}
        if "door_width" in got and "door_height" not in got and "door_height" in missing and photo_bytes is None:
            got["door_height"] = measurement(DOOR_HEIGHT_IN, DOOR_HEIGHT_ERR_IN, "estimated:standard_door")
        m.update(got)
        missing = [k for k in KEYS if k not in m]
        meth = res["method"]
        records.append(audit(
            "estimate_room",
            source={"kind": "lidar_scan", "file": scan_name, "outline_in": res["outline_in"], "walls": res["walls"],
                    "doors": res["doors"], "ceiling_in": res["ceiling_in"], "area_sqft": res["area_sqft"],
                    "method": meth},
            input={"scan": scan_name, "exact": sorted(exact)},
            decision=f"scanned {len(res['walls'])}-wall room, {res['area_sqft']:g} sq ft: "
                     + ", ".join(f"{k} {got[k]['value_in']:g} ±{got[k]['error_in']:g} in" for k in got),
            status="measured",
            why=(f"LiDAR mesh ({meth['vertices']} vertices, {meth['units']}, {meth['up_axis']}-up): floor and "
                 f"walls found as planes, outline traced and snapped to {meth['wall_points']} wall points "
                 f"(spread {meth['edge_spread_mad_in']:g} in, so error ±{res['error_in']:g} in). Wall = longest "
                 f"wall {res['longest_wall']}; depth = straight out from its middle to the opposite wall. "
                 + ("" if res["doors"] else "No open doorway in the scan (closed doors are flush with the wall), "
                    "so the door needs the photo or a tape measure. ")
                 + ("Door height assumed 80 in (standard US door). " if
                    got.get("door_height", {}).get("source") == "estimated:standard_door" else "")).strip()))

    if missing and photo_bytes is None:
        if missing == ["depth"]:
            pass  # depth falls back to the explicit default below
        else:
            raise ValueError("no room photo, so these measurements are needed in inches: " + ", ".join(missing))

    if missing and photo_bytes is not None and missing != ["depth"]:
        try:
            est, source, why = _from_photo(photo_bytes)
        except DetectionError as e:
            raise ValueError(f"couldn't estimate the room from the photo ({e}); give these in inches: "
                             + ", ".join(k for k in missing if k != "depth")) from None
        used = [k for k in missing if k in est]
        for k in used:
            m[k] = est[k]
        still = [k for k in missing if k not in m and k != "depth"]
        if still:
            raise ValueError("the photo didn't give these; give them in inches: " + ", ".join(still))
        records.append(audit(
            "estimate_room", source=source,
            input={"labels": LABELS, "exact": sorted(exact)},
            decision="estimated " + ", ".join(f"{k} {m[k]['value_in']:g} ±{m[k]['error_in']:g} in" for k in used),
            status="estimated", why=why))

    if "depth" not in m:
        m["depth"] = measurement(DEFAULT_DEPTH_IN, DEFAULT_DEPTH_IN * DEFAULT_DEPTH_ERR, "estimated:default")
        records.append(audit(
            "estimate_room", source={"kind": "template"},
            decision=f"depth {DEFAULT_DEPTH_IN:g} ±{DEFAULT_DEPTH_IN * DEFAULT_DEPTH_ERR:g} in (rough default)",
            status="estimated",
            why="room depth isn't visible in a photo and wasn't given; this is a rough default with 25% error. "
                "Measure the depth to make walkway checks exact."))

    if exact:
        records.append(audit(
            "estimate_room", source={"kind": "template"}, input={"exact": {k: exact[k] for k in sorted(exact)}},
            decision="used the person's measurements for " + ", ".join(sorted(exact)),
            status="exact", why="typed by the person; error 0, they override any photo estimate."))

    return make_room(m["wall"], m["depth"], m["door_width"], m["door_height"]), records


def is_roomplan(path: str) -> bool:
    """True for a RoomPlan-style GLB (Polycam Floorplan): named Wall_* objects. Read with alistair's fit.scan."""
    import json as _json
    import struct as _struct
    try:
        with open(path, "rb") as fh:
            head = fh.read(20)
            if head[:4] != b"glTF":
                return False
            clen = _struct.unpack_from("<I", head, 12)[0]
            js = _json.loads(fh.read(clen))
    except (OSError, ValueError):
        return False
    return any((n.get("name") or "").startswith("Wall_") for n in js.get("nodes", []))


def estimate_roomplan(path: str, scan_wall: str | None = None, exact: dict | None = None) -> tuple[dict, list[dict]]:
    """Room measurements from a RoomPlan GLB via alistair's fit.scan.load_scan (walls, doors, existing furniture).

    wall = scan_wall's inner length (default: the longest wall); depth = the room's inner extent straight out from
    that wall; door = the narrowest door (what furniture must get through). Source "scanned:roomplan", error 1 in.
    exact values (source "user") override key by key, e.g. a tape-measured wall section.
    """
    from fit.scan import load_scan
    sc = load_scan(path)
    walls = sc["walls"]
    if not walls:
        raise ValueError(f"no walls in {path}")
    wl = (lambda w: w.get("inner_length_in") or w["length_in"])
    chosen = next((w for w in walls if w["id"] == scan_wall), None) if scan_wall else max(walls, key=wl)
    if chosen is None:
        raise ValueError(f"no wall {scan_wall!r} in the scan; walls are "
                         + ", ".join(f'{w["id"]} {wl(w):g} in' for w in walls))
    xs, zs = [q[0] for q in sc["outline"]], [q[1] for q in sc["outline"]]
    (ax, az), (bx, bz) = chosen["a"], chosen["b"]
    depth = (max(zs) - min(zs)) if abs(az - bz) < abs(ax - bx) else (max(xs) - min(xs))
    m = {"wall": measurement(round(wl(chosen), 1), 1.0, "scanned:roomplan"),
         "depth": measurement(round(depth, 1), 1.0, "scanned:roomplan")}
    doors = sorted((d for d in sc["doors"] if d.get("kind", "door") == "door"), key=lambda d: d["width_in"])
    if doors:
        m["door_width"] = measurement(doors[0]["width_in"], 1.0, "scanned:roomplan")
        m["door_height"] = measurement(doors[0]["height_in"], 1.0, "scanned:roomplan")
    for k, v in (exact or {}).items():
        if v is not None:
            m[k] = measurement(float(v), 0.0, "user")
    rec = audit(
        "estimate_room",
        source={"kind": "lidar_scan", "reader": "fit.scan (RoomPlan)", "file": path,
                "walls": [{"id": w["id"], "inner_length_in": wl(w)} for w in walls], "doors": sc["doors"],
                "existing_items": [{"id": i["id"], "category": i["category"], "w_in": i["w_in"], "d_in": i["d_in"]}
                                   for i in sc["items"]]},
        input={"scan": path, "scan_wall": chosen["id"], "exact": sorted(k for k, v in (exact or {}).items() if v is not None)},
        decision="scanned room: " + ", ".join(f'{k} {v["value_in"]:g} ±{v["error_in"]:g} in ({v["source"]})'
                                             for k, v in m.items()),
        status="measured",
        why=(f'RoomPlan scan with {len(walls)} named walls, {len(sc["doors"])} door(s), {len(sc["items"])} existing '
             f'items. Wall = {chosen["id"]} (inner face); depth = inner extent out from it; door = narrowest door.'
             + (" Exact values typed by the person override the scan." if exact else "")))
    missing = [k for k in ("door_width", "door_height") if k not in m]
    if missing:
        raise ValueError(f"the scan has no door; give {missing} as exact measurements")
    return make_room(m["wall"], m["depth"], m["door_width"], m["door_height"]), [rec]
