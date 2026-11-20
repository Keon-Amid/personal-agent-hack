"""Make a 3D model of a catalog product from its IKEA photo, for the 3D room (web/src/room3d).

  python3 scripts/make_model.py <product_id> [<product_id> ...]
  python3 scripts/make_model.py --plan contracts/plan.live.json      # every non-rug item in a plan

Steps, per product:
  1. Send the product's main IKEA photo (image_url in data/products.json) to Hyper3D Rodin (image -> 3D).
     Costs Hyper3D credits (0.5 per model at tier Gen-2.5-Low on Nov 20, 2026). Needs HYPER3D_API_KEY in .env.
  2. Save the raw model in .cache/models_raw/ (gitignored, 10-26 MB each). A cached raw model is reused,
     so re-running never pays twice. --force regenerates.
  3. Shrink it with Blender (scripts/shrink_model.py) into web/public/models/<product_id>.glb (about 1 MB).
  4. Record it in web/public/models/index.json, with the turn needed so its width/depth line up with the
     catalog's, and how far its own proportions are from the listed size ("stretch").

The renderer stretches every model to the product's listed width x depth x height, so the picture agrees with
the fit maths. A big stretch number means the generated shape was off and will look distorted.

Stdlib only. No model is faked: if a step fails the product simply keeps its simple box shape in the room.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".cache" / "models_raw"
OUT = ROOT / "web" / "public" / "models"
API = os.environ.get("HYPER3D_API", "https://api.hyper3d.com/api/v2")
TIER = os.environ.get("HYPER3D_TIER", "Gen-2.5-Low")  # Basic API access allows Gen-2.5-Low and Gen-2.5-Extreme-Low
UA = "Mozilla/5.0 (room-furnisher hackathon script)"  # IKEA and Cloudflare reject urllib's default agent
SKIP_CATEGORIES = {"rug"}  # flat: the renderer's own flat box is already right
MAX_TRIS = {"default": 20000, "floor_lamp": 8000, "side_table": 10000, "coffee_table": 12000}


def load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from {url.split('?')[0]}: {e.read()[:300].decode('utf-8', 'replace')}") from None


def api(path: str, key: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    return json.loads(http(f"{API}/{path}", body, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}))


def submit(key: str, image: bytes) -> dict:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="images"; filename="0000.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n".encode() + image + b"\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="tier"\r\n\r\n{TIER}\r\n'.encode(),
        f"--{boundary}--\r\n".encode(),
    ]
    out = http(f"{API}/rodin", b"".join(parts),
               {"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(out)


def generate(product: dict, key: str, raw: Path) -> None:
    image = http(product["image_url"])
    job = submit(key, image)
    if not job.get("uuid"):
        raise RuntimeError(f"Hyper3D refused the job: {job.get('error')} {job.get('message')}")
    print(f"  submitted {job['uuid']} (credits consumed: {job.get('consumed')})", flush=True)
    sub = job["jobs"]["subscription_key"]
    deadline = time.time() + 600
    while True:
        states = [j.get("status") for j in api("status", key, {"subscription_key": sub}).get("jobs", [])]
        if states and all(s == "Done" for s in states):
            break
        if any(s == "Failed" for s in states):
            raise RuntimeError(f"Hyper3D job failed: {states}")
        if time.time() > deadline:
            raise RuntimeError(f"Hyper3D job still running after 10 minutes: {states}")
        time.sleep(6)
    files = api("download", key, {"task_uuid": job["uuid"]}).get("list", [])
    glb = next((f for f in files if str(f.get("name", "")).lower().endswith(".glb")), None)
    if not glb:
        raise RuntimeError(f"no .glb in the download list: {[f.get('name') for f in files]}")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(http(glb["url"]))
    print(f"  downloaded raw model, {raw.stat().st_size / 1e6:.1f} MB", flush=True)


def glb_size(path: Path) -> tuple[float, float, float]:
    """Width (x), height (y), depth (z) of a .glb from its POSITION bounds. Node transforms are ignored."""
    data = path.read_bytes()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise RuntimeError(f"{path.name} is not a .glb file")
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON":
        raise RuntimeError(f"{path.name}: first chunk is not JSON")
    doc = json.loads(data[20:20 + chunk_len])
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            lo = [min(a, b) for a, b in zip(lo, acc["min"])]
            hi = [max(a, b) for a, b in zip(hi, acc["max"])]
    return tuple(h - l for l, h in zip(lo, hi))  # type: ignore[return-value]


def turn_and_stretch(size: tuple[float, float, float], dims: dict) -> tuple[int, list[float]]:
    """Pick 0 or 90 degrees so the model's footprint lines up with the listed width/depth; report the stretch."""
    sx, sy, sz = size
    w, d, h = dims["w"], dims["d"], dims["h"] or sy

    def stretch(mw: float, md: float) -> list[float]:
        f = [w / mw, d / md, h / sy]
        g = (f[0] * f[1] * f[2]) ** (1 / 3)
        return [round(v / g, 2) for v in f]

    straight, turned = stretch(sx, sz), stretch(sz, sx)
    worst = lambda s: max(abs(v - 1) for v in s)  # noqa: E731
    return (90, turned) if worst(turned) < worst(straight) - 0.02 else (0, straight)


def find_blender() -> str | None:
    cands = [os.environ.get("BLENDER"), shutil.which("blender"),
             *sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True),
             "/Applications/Blender.app/Contents/MacOS/Blender"]
    return next((c for c in cands if c and Path(c).exists()), None)


def shrink(raw: Path, out: Path, category: str) -> bool:
    blender = find_blender()
    if not blender:
        print("  Blender not found (set BLENDER=/path/to/blender): cannot shrink, model NOT added", flush=True)
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    tris = MAX_TRIS.get(category, MAX_TRIS["default"])
    r = subprocess.run([blender, "-b", "--factory-startup", "-P", str(ROOT / "scripts" / "shrink_model.py"),
                        "--", str(raw), str(out), str(tris), "1024"], capture_output=True, text=True, errors="replace")
    line = next((l for l in r.stdout.splitlines() if l.startswith("SHRUNK")), None)
    if r.returncode != 0 or not line or not out.exists():
        print(f"  shrink failed (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}", flush=True)
        return False
    print("  " + line, flush=True)
    return True


def main(argv: list[str]) -> int:
    load_env()
    flags = {a for a in argv if a.startswith("--") and a not in ("--plan",)}
    force, no_shrink, no_generate = "--force" in flags, "--no-shrink" in flags, "--no-generate" in flags
    catalog = {p["id"]: p for p in json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))["products"]}
    ids: list[str] = []
    args = [a for a in argv if a not in flags]
    while args:
        a = args.pop(0)
        if a == "--plan":
            plan = json.loads(Path(args.pop(0)).read_text(encoding="utf-8"))
            ids += [it.get("product_id") or it["product"]["id"] for it in plan["items"]]
        else:
            ids.append(a)
    ids = list(dict.fromkeys(ids))
    if not ids:
        print(__doc__)
        return 2
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    key = os.environ.get("HYPER3D_API_KEY", "").strip()
    failed = 0
    for pid in ids:
        p = catalog.get(pid)
        if not p:
            print(f"{pid}: not in data/products.json, skipped"); failed += 1; continue
        if p["category"] in SKIP_CATEGORIES:
            print(f"{pid}: {p['category']} is drawn as a flat box, skipped"); continue
        print(pid, flush=True)
        raw, out = RAW / f"{pid}.glb", OUT / f"{pid}.glb"
        try:
            if force or not raw.exists():
                if no_generate:
                    print("  no cached raw model and --no-generate given, skipped"); continue
                if not key:
                    raise RuntimeError("HYPER3D_API_KEY is not set (put it in .env)")
                generate(p, key, raw)
            else:
                print(f"  using cached raw model ({raw.stat().st_size / 1e6:.1f} MB)", flush=True)
            if no_shrink:
                continue
            if (force or not out.exists() or out.stat().st_mtime < raw.stat().st_mtime) and not shrink(raw, out, p["category"]):
                failed += 1
                continue
            rot, stretch = turn_and_stretch(glb_size(raw), p["dims_in"])
            if index_path.exists():  # re-read: another run may have added entries meanwhile
                index = json.loads(index_path.read_text(encoding="utf-8"))
            index[pid] = {"file": out.name, "source": f"AI-generated from the IKEA photo (Hyper3D Rodin {TIER})",
                          "rot_y_deg": rot, "stretch_w_d_h": stretch, "bytes": out.stat().st_size}
            index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
            print(f"  added: turn {rot} deg, stretch w/d/h {stretch}, {out.stat().st_size / 1e6:.2f} MB", flush=True)
        except Exception as e:  # one bad product must not stop the rest
            print(f"  FAILED: {e}", flush=True)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
