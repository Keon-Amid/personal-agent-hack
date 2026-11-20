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


RERANKER = "Qwen/Qwen3-Reranker-4B"
STYLES = ["warm minimal", "scandinavian", "mid-century modern", "industrial", "bohemian eclectic",
          "traditional", "dark modern", "coastal"]
RRF_K = 60  # reciprocal rank fusion constant (the usual default)


def product_text(p: dict) -> str:
    """What the reranker reads: IKEA's own name, colour, material and description."""
    return (f'{p["name"]}. Color: {p.get("color") or "n/a"}. Material: {p.get("material") or "n/a"}. '
            f'{p.get("description") or ""}')


def score(query: str, items: list[dict], model: str = RERANKER) -> dict[str, float]:
    """POST /v1/score/{model}: relevance of each item's text to the query. Returns {item_id: score}."""
    url = f"{API}/v1/score/{urllib.parse.quote(model, safe='')}"
    body = json.dumps({"query": {"text": query}, "items": items}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    return {s["item_id"]: s["score"] for s in out["scores"]}


def rerank(products: list[dict], category: str, style_text: str) -> list[dict]:
    """Superlinked reranker over IKEA's product text, best first."""
    ps = [p for p in products if p["category"] == category]
    s = score(style_text, [{"id": p["id"], "text": product_text(p)} for p in ps])
    out = [{"id": p["id"], "name": p["name"], "text_score": round(s.get(p["id"], 0.0), 4)} for p in ps]
    return sorted(out, key=lambda o: -o["text_score"])


def detect_style(room_vec: list[float], styles: list[str] = STYLES) -> list[dict]:
    """Zero-shot: which style label is the room photo closest to? (SigLIP text<->image, one API call)."""
    vecs = encode([{"text": f"a photo of a {s} living room"} for s in styles])
    out = [{"style": s, "score": round(cosine(room_vec, v), 4)} for s, v in zip(styles, vecs)]
    return sorted(out, key=lambda o: -o["score"])


def product_styles(emb: dict, styles: list[str] = STYLES, top: int = 3) -> dict:
    """Zero-shot style labels per product photo (one API call for the label texts). Not hand-written:
    SigLIP scores each stored product photo against "a photo of {style} furniture". Scores are cosine
    similarity; under ~0.05 the label is weak (rugs and lamps mostly land there)."""
    vecs = encode([{"text": f"a photo of {s} furniture"} for s in styles])
    out = {}
    for pid, pv in emb["vectors"].items():
        sc = sorted(({"style": s, "score": round(cosine(pv, v), 4)} for s, v in zip(styles, vecs)),
                    key=lambda o: -o["score"])
        out[pid] = sc[:top]
    return out


def analyze_room(room_photo: bytes | None = None, style_text: str | None = None) -> dict:
    """Do the room's Superlinked calls once, then pass the result to style_match for every slot.

    Returns {"vec", "style_text", "detected_style"}: 2 API calls for a photo (embed + style labels), 1 for text.
    """
    if room_photo is not None:
        vec = query_photo(room_photo)
        detected = None
        if not style_text:
            detected = detect_style(vec)
            style_text = f"{detected[0]['style']} style living room"
        return {"vec": vec, "style_text": style_text, "detected_style": detected}
    if style_text:
        return {"vec": query_text(style_text), "style_text": style_text, "detected_style": None}
    raise ValueError("need room_photo or style_text")


def style_match(products: list[dict], category: str, emb: dict,
                room_photo: bytes | None = None, style_text: str | None = None,
                room: dict | None = None) -> dict:
    """The full Superlinked style step for one category.

    1. Room photo -> SigLIP vector -> detected style (if no style_text given).
    2. Photo match: product photos vs the room photo (or the style text).
    3. Text match: Superlinked reranker over IKEA's descriptions vs the style text.
    4. Fuse the two rankings with reciprocal rank fusion, so neither score scale dominates.
    Every product gets both ranks and scores, ready for the audit trail.
    Pass `room=analyze_room(...)` to reuse one room analysis across slots (then only the rerank call is made).
    """
    room = room or analyze_room(room_photo, style_text)
    q, style_text, detected = room["vec"], room["style_text"], room["detected_style"]
    by_photo = rank(products, category, q, emb)
    by_text = rerank(products, category, style_text)
    pr = {o["id"]: (i + 1, o["style_score"]) for i, o in enumerate(by_photo)}
    tr = {o["id"]: (i + 1, o["text_score"]) for i, o in enumerate(by_text)}
    fused = []
    for o in by_photo:
        (p_rank, p_score), (t_rank, t_score) = pr[o["id"]], tr.get(o["id"], (len(tr) + 1, 0.0))
        fused.append({
            "id": o["id"], "name": o["name"],
            "product_styles": (emb.get("product_styles") or {}).get(o["id"], []),
            "style_fused": round(1 / (RRF_K + p_rank) + 1 / (RRF_K + t_rank), 6),
            "photo_rank": p_rank, "photo_score": p_score, "text_rank": t_rank, "text_score": t_score,
        })
    fused.sort(key=lambda o: -o["style_fused"])
    for i, o in enumerate(fused, 1):
        o["style_rank"] = i
    return {
        "category": category, "style_text": style_text, "detected_style": detected,
        "source": {"kind": "superlinked", "embed_model": emb["model"], "rerank_model": RERANKER,
                   "fusion": f"reciprocal rank fusion, k={RRF_K}"},
        "ranked": fused,
    }


def query_text(text: str) -> list[float]:
    return encode([{"text": text}])[0]


def query_photo(data: bytes, fmt: str = "jpeg") -> list[float]:
    return encode([image_item(data, fmt)])[0]


if __name__ == "__main__":
    products = json.loads((HERE / "products.json").read_text())["products"]
    a = sys.argv[1:]
    if a[:2] == ["build", "--missing"]:  # embed only products not in the file yet
        emb = json.loads(EMB_PATH.read_text())
        new = [p for p in products if p["id"] not in emb["vectors"]]
        if new:
            emb["vectors"].update(build(new)["vectors"])
        emb["product_styles"] = product_styles(emb)
        EMB_PATH.write_text(json.dumps(emb))
        print(f"embedded {len(new)} new products; {len(emb['vectors'])} total")
    elif a[:1] == ["build"]:
        emb = build(products)
        emb["product_styles"] = product_styles(emb)
        EMB_PATH.write_text(json.dumps(emb))
        print(f"embedded {len(emb['vectors'])} products with {emb['model']} -> {EMB_PATH.name}")
    elif a[:1] == ["labels"]:  # add/refresh style labels without re-embedding the photos
        emb = json.loads(EMB_PATH.read_text())
        emb["product_styles"] = product_styles(emb)
        EMB_PATH.write_text(json.dumps(emb))
        print(f"labelled {len(emb['product_styles'])} products")
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
