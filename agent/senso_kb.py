"""Load the product catalog (and optionally the room rules) into Senso's knowledge base, idempotently.

One raw-text document per product, built only from data/products.json (numbers read from IKEA pages), so Senso
can verify every spec, box size and price the agent states. Stdlib only. Needs SENSO_API_KEY (the team's org,
the same one the fact-checks run against).

    python3 agent/senso_kb.py load            # products (skips ones already loaded with the same text)
    python3 agent/senso_kb.py load --rules    # also the room-rules doc
    python3 agent/senso_kb.py status          # poll processing status of everything in the index
    python3 agent/senso_kb.py search "KIVIK width"

data/senso_index.json maps product id -> {title, sha256, kb_node_id, status}. Senso returns 409 for identical
text, so re-running never duplicates documents.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://apiv2.senso.ai/api/v1"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) personal-agent-hack/1.0"  # Senso's Cloudflare 403s urllib's UA
ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "data" / "products.json"
INDEX = ROOT / "data" / "senso_index.json"

RULES_TITLE = "Room rules (team defaults for this app)"
RULES_TEXT = """Room rules used by the furnishing agent. These are the team's chosen defaults, not a building code.
- Walkway: keep at least 36 inches of clear walkway in front of any item placed against a wall.
- Wall fit: an item placed on a wall must be no wider than that wall.
- Doorway: every package (box) of an item must fit through the room's door: its smallest side within the door width
  and its middle side within the door height. Items that ship assembled are checked with their assembled size.
- Rugs: keep a rug at least 6 inches from every wall.
- Measurements estimated from a photo carry an error margin; if the answer depends on that margin, ask the person
  to measure that one thing before deciding."""

BEDROOM_RULES_TITLE = "Room rules: bedroom (team defaults)"
BEDROOM_RULES_TEXT = """Bedroom rules used by the furnishing agent. These are the team's chosen defaults, not a building code.
- Bed sides: keep at least 24 inches of clear floor beside each side of the bed that someone gets in or out from.
  A twin or full bed may go against a wall on one side; the open side still needs 24 inches.
- Foot of bed: keep at least 24 inches of clear floor between the foot of the bed and the wall or the next item.
- Dresser: keep at least 36 inches of clear floor in front of a dresser or chest so the drawers open and a person
  can stand in front of them.
- Wardrobe: keep at least 36 inches of clear floor in front of a wardrobe with hinged doors, and at least
  24 inches in front of one with sliding doors.
- Nightstand height: the nightstand top should be within 4 inches of the mattress top (above or below).
- Nightstand gap: put a nightstand no more than 6 inches from the side of the bed.
- Door: nothing on the floor inside the room door's swing, and at least 36 inches of clear floor from the doorway to
  the nearest furniture.
- Window: if the bedroom window is the emergency escape opening, nothing taller than the window sill may stand
  directly in front of it.
- Code fact (US IRC R310, not a team default): every sleeping room needs one operable emergency escape opening with a
  net clear opening of at least 5.7 square feet (5 square feet at grade floor or below-grade), at least 24 inches
  high and 20 inches wide, with the sill no more than 44 inches above the floor. Local codes can differ.
- Measurements estimated from a photo carry an error margin; if the answer depends on that margin, ask the person
  to measure that one thing before deciding."""


def _key() -> str:
    k = os.environ.get("SENSO_API_KEY")
    env = ROOT / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SENSO_API_KEY="):
                k = line.split("=", 1)[1].split("#")[0].strip()
    if not k:
        raise SystemExit("SENSO_API_KEY is not set (put the team's key in .env)")
    return k


def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-API-Key": _key(), "Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}


def _in(v) -> str:
    return "unknown" if v is None else f"{v:g} in"


def product_doc(p: dict) -> tuple[str, str]:
    """(title, text) for one product. Facts only, all from the catalog; nothing inferred."""
    d = p["dims_in"]
    lines = [
        f'{p["name"]} (IKEA article {p["article_number"]}).',
        f'Category: {p["category"].replace("_", " ")}.',
        f'Size: width {_in(d["w"])}, depth {_in(d["d"])}, height {_in(d["h"])}.',
    ]
    if p.get("packages_in"):
        boxes = "; ".join(f'box {i}: {_in(b["w"])} wide x {_in(b["d"])} long x {_in(b["h"])} high'
                          for i, b in enumerate(p["packages_in"], 1))
        lines.append(f'Ships in {len(p["packages_in"])} package(s): {boxes}.')
    if p.get("price_usd") is not None:
        lines.append(f'Price on the IKEA US page on {p["fetched_at"][:10]}: ${p["price_usd"]:g}.')
    else:
        lines.append("The IKEA US page showed no price.")
    if p.get("rating") is not None:
        lines.append(f'IKEA customer rating: {p["rating"]:g} out of 5 from {p["review_count"]} reviews.')
    if p.get("color"):
        lines.append(f'Color: {p["color"]}.')
    if p.get("material"):
        lines.append(f'Material: {p["material"]}.')
    lines.append(f'Source: {p["source_url"]}')
    return f'IKEA {p["article_number"]} {p["name"]}', "\n".join(lines)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load(products: list[dict], index: dict, rules: bool = False) -> dict:
    """Create missing/changed documents. Returns counts. Updates `index` in place."""
    docs = [(p["id"], *product_doc(p)) for p in products]
    if rules:
        docs.append(("_rules", RULES_TITLE, RULES_TEXT))
        docs.append(("_bedroom_rules", BEDROOM_RULES_TITLE, BEDROOM_RULES_TEXT))
    counts = {"created": 0, "unchanged": 0, "already_in_senso": 0, "failed": 0}
    for pid, title, text in docs:
        h = sha(text)
        cur = index.get(pid)
        if cur and cur.get("sha256") == h and cur.get("kb_node_id"):
            counts["unchanged"] += 1
            continue
        code, out = _req("POST", "/org/kb/raw", {"title": title, "text": text})
        if code in (200, 201, 202):
            index[pid] = {"title": title, "sha256": h, "kb_node_id": out.get("kb_node_id"),
                          "content_id": out.get("id"), "status": out.get("processing_status", "processing")}
            counts["created"] += 1
        elif code == 409:  # identical text already in the org (loaded earlier, maybe by a teammate)
            index[pid] = {**(cur or {}), "title": title, "sha256": h, "status": "exists_in_senso"}
            counts["already_in_senso"] += 1
        else:
            print(f"FAILED {pid}: HTTP {code} {out.get('message') or out}", file=sys.stderr)
            counts["failed"] += 1
            if code in (401, 402, 403):
                break  # bad key / out of credits: stop instead of failing 44 times
    return counts


def poll(index: dict, timeout_s: int = 180) -> dict:
    """Poll processing status until every created doc is complete/failed (or timeout)."""
    end = time.time() + timeout_s
    pending = [k for k, v in index.items() if v.get("kb_node_id") and v.get("status") not in ("complete", "failed")]
    while pending and time.time() < end:
        for pid in list(pending):
            code, out = _req("GET", f'/org/kb/nodes/{index[pid]["kb_node_id"]}')
            st = ((out.get("content") or {}).get("processing_status")) if code == 200 else None
            if st in ("complete", "failed"):
                index[pid]["status"] = st
                pending.remove(pid)
        if pending:
            time.sleep(5)
    return {"complete": sum(v.get("status") == "complete" for v in index.values()),
            "failed": sum(v.get("status") == "failed" for v in index.values()), "still_processing": len(pending)}


def search(query: str) -> list[dict]:
    code, out = _req("POST", "/org/search/context", {"query": query})
    if code != 200:
        raise SystemExit(f"search failed: HTTP {code} {out}")
    return [{"title": r.get("title"), "score": r.get("score"), "chunk_text": r.get("chunk_text")}
            for r in out.get("results", [])]


if __name__ == "__main__":
    a = sys.argv[1:]
    idx = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    if a[:1] == ["load"]:
        prods = json.loads(PRODUCTS.read_text())["products"]
        print(load(prods, idx, rules="--rules" in a))
        INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False))
        print(poll(idx))
        INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    elif a[:1] == ["status"]:
        print(poll(idx, timeout_s=30))
        INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    elif a[:1] == ["search"] and len(a) > 1:
        for r in search(" ".join(a[1:])):
            print(f'{r["score"]}  {r["title"]}\n    {(r["chunk_text"] or "")[:200]}')
    else:
        print(__doc__)
