"""Style matching with Superlinked SIE (hosted). Stdlib only; reads SIE_API_KEY from the environment or .env.

SigLIP puts images and text in one space, so a product photo can be compared with the room photo or with a
style description ("warm minimal, light oak"). Product photos are embedded once into data/style_embeddings.json.

    python3 data/sie.py build                         # embed every product's main photo (needs SIE_API_KEY)
    python3 data/sie.py rank sofa "warm minimal light wood"
    python3 data/sie.py rank sofa --photo room.jpg
"""
from __future__ import annotations

import base64
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.superlinked.com"
MODEL = "google/siglip-so400m-patch14-384"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
HERE = Path(__file__).parent
EMB_PATH = HERE / "style_embeddings.json"


def _key() -> str:
    k = os.environ.get("SIE_API_KEY")
    env = HERE.parent / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SIE_API_KEY="):
                k = line.split("=", 1)[1].split("#")[0].strip()
    if not k:
        raise SystemExit("SIE_API_KEY is not set (put it in .env)")
    return k


def encode(items: list[dict], model: str = MODEL) -> list[list[float]]:
    """POST /v1/encode/{model}. items: [{"text": ...}] or [{"images": [{"data": b64, "format": "jpeg"}]}]."""
    url = f"{API}/v1/encode/{urllib.parse.quote(model, safe='')}"
    body = json.dumps({"items": items, "params": {"output_types": ["dense"]}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    vecs = []
    for it in out["items"]:
        d = it["dense"]
        vecs.append(d["values"] if isinstance(d, dict) else d)
    return vecs


def image_item(data: bytes, fmt: str = "jpeg") -> dict:
    return {"images": [{"data": base64.b64encode(data).decode(), "format": fmt}]}


def fetch_image(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def build(products: list[dict], batch: int = 8) -> dict:
    vecs: dict[str, list[float]] = {}
    for i in range(0, len(products), batch):
        chunk = products[i:i + batch]
        got = encode([image_item(fetch_image(p["image_url"])) for p in chunk])
        for p, v in zip(chunk, got):
            vecs[p["id"]] = [round(x, 6) for x in v]
    return {"model": MODEL, "input": "image_url (IKEA main product photo)",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "vectors": vecs}


def rank(products: list[dict], category: str, query_vec: list[float], emb: dict) -> list[dict]:
    """Products in a category, most similar to the query first. score = cosine similarity (SigLIP)."""
    out = [{"id": p["id"], "name": p["name"], "style_score": round(cosine(query_vec, emb["vectors"][p["id"]]), 4),
            "style_source": {"kind": "superlinked", "model": emb["model"]}}
           for p in products if p["category"] == category and p["id"] in emb["vectors"]]
    return sorted(out, key=lambda o: -o["style_score"])


def query_text(text: str) -> list[float]:
    return encode([{"text": text}])[0]


def query_photo(data: bytes, fmt: str = "jpeg") -> list[float]:
    return encode([image_item(data, fmt)])[0]


if __name__ == "__main__":
    products = json.loads((HERE / "products.json").read_text())["products"]
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        emb = build(products)
        EMB_PATH.write_text(json.dumps(emb))
        print(f"embedded {len(emb['vectors'])} products with {emb['model']} -> {EMB_PATH.name}")
    elif a[:1] == ["rank"] and len(a) >= 3:
        emb = json.loads(EMB_PATH.read_text())
        if a[2] == "--photo":
            p = Path(a[3])
            q = query_photo(p.read_bytes(), "png" if p.suffix.lower() == ".png" else "jpeg")
        else:
            q = query_text(" ".join(a[2:]))
        for o in rank(products, a[1], q, emb):
            print(f'{o["style_score"]:.4f}  {o["name"]}')
    else:
        print(__doc__)
