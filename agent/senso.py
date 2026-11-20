"""Senso fact-check client: check(text, question) -> SensoCheck, build_claim(item), verdict_ok(check).

Senso verifies facts that live in its knowledge base (product specs, box sizes, prices, the loaded room rules).
It does not do room arithmetic; fit/ decides fit. So build_claim only states KB-checkable facts.

POST /org/evals/text with wait=true (~7 s, no credits). If the run is not finished, poll
GET /org/evals/runs/{id} every 5 s for up to 60 s. Results are cached on disk by sha256(text + question)
under ~/.cache/room-furnisher/senso/ (override with ROOM_FURNISHER_SENSO_CACHE), outside the repo.
Stdlib only. Senso sits behind Cloudflare, which 403s ("error code: 1010") without a browser-ish User-Agent.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

API = "https://apiv2.senso.ai/api/v1"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) personal-agent-hack/1.0"
ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "data" / "products.json"
POLL_EVERY_S = 5
POLL_MAX_S = 60

# Rule sentences, worded like the loaded "Room Furnisher clearance rules" doc so Senso can match them.
RULE_WALKWAY = "Our rules require 36 inches of clear walkway in front of any item placed against a wall."
RULE_DOORWAY = "Our rules require every shipping box to fit through the doorway."
RULE_RUG = "Our rules require a rug to be at least 6 inches from every wall."
RULE_SOFA_WALL = "Our rules place the sofa on the longest wall."


class SensoError(RuntimeError):
    pass


# --- HTTP layer (tests replace `_http`) -------------------------------------------------------------------

def _key() -> str:
    k = os.environ.get("SENSO_API_KEY")
    env = ROOT / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SENSO_API_KEY="):
                k = line.split("=", 1)[1].split("#")[0].strip().strip('"').strip("'")
    if not k:
        raise SensoError("SENSO_API_KEY is not set (put the team's key in .env)")
    return k


def _urllib_http(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-API-Key": _key(), "Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}


_http: Callable[[str, str, dict | None], tuple[int, dict]] = _urllib_http
_sleep: Callable[[float], None] = time.sleep


# --- cache -------------------------------------------------------------------------------------------------

def _cache_dir() -> Path:
    return Path(os.environ.get("ROOM_FURNISHER_SENSO_CACHE")
                or Path.home() / ".cache" / "room-furnisher" / "senso")


def _cache_key(text: str, question: str) -> str:
    return hashlib.sha256((text + "\n" + question).encode()).hexdigest()


# --- check -------------------------------------------------------------------------------------------------

def _quote(c: dict) -> str | None:
    q = c.get("quote")
    if q:
        return q
    for ev in c.get("evidence") or []:
        if isinstance(ev, dict) and (ev.get("quote") or ev.get("content") or ev.get("text")):
            return ev.get("quote") or ev.get("content") or ev.get("text")
    return None


def _parse(run: dict) -> dict:
    claims = [{"claim": c.get("claim_text") or c.get("claim") or "",
               "verdict": c.get("verdict") or "not_verifiable",
               "quote": _quote(c)}
              for c in run.get("claims") or []]
    acc = run.get("accuracy_pct")
    if acc is None:
        acc = (run.get("metrics") or {}).get("accuracy_pct")
    return {"check_id": run.get("eval_run_id") or run.get("id") or "",
            "accuracy_pct": float(acc) if acc is not None else None,
            "claims": claims}


def _finished(run: dict) -> bool:
    return bool(run.get("claims")) or run.get("status") in ("completed", "failed", "error")


def check(text: str, question: str) -> dict:
    """Fact-check `text` against the Senso KB. Returns SensoCheck {check_id, accuracy_pct, claims, cached}.

    Raises SensoError on HTTP errors, a missing key, or a run that never finishes (no fake results)."""
    path = _cache_dir() / f"{_cache_key(text, question)}.json"
    try:
        hit = json.loads(path.read_text())
        return {**hit, "cached": True}
    except (OSError, json.JSONDecodeError):
        pass

    code, run = _http("POST", "/org/evals/text",
                      {"text": text, "author": "ai_assistant", "question": question, "wait": True})
    if code not in (200, 201, 202):
        raise SensoError(f"Senso eval failed: HTTP {code} {run.get('message') or run}")
    run_id = run.get("eval_run_id") or run.get("id")
    waited = 0
    while not _finished(run):
        if not run_id or waited >= POLL_MAX_S:
            raise SensoError(f"Senso eval {run_id} not finished after {waited} s")
        _sleep(POLL_EVERY_S)
        waited += POLL_EVERY_S
        code, run = _http("GET", f"/org/evals/runs/{run_id}", None)
        if code != 200:
            raise SensoError(f"Senso eval poll failed: HTTP {code} {run.get('message') or run}")
    if run.get("status") in ("failed", "error"):
        raise SensoError(f"Senso eval {run_id} ended with status {run.get('status')}")

    out = _parse(run)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out))
        tmp.replace(path)
    except OSError:
        pass  # cache is an optimisation only
    return {**out, "cached": False}


# --- claim + verdict ---------------------------------------------------------------------------------------

_catalog: dict | None = None


def _product(pid: str) -> dict | None:
    global _catalog
    if _catalog is None:
        try:
            d = json.loads(PRODUCTS.read_text())
            _catalog = {p["id"]: p for p in (d["products"] if isinstance(d, dict) else d)}
        except (OSError, json.JSONDecodeError, KeyError):
            _catalog = {}
    return _catalog.get(pid)


def _n(v: float) -> str:
    return f"{v:g}"


def build_claim(item: dict) -> str:
    """KB-checkable facts about the picked item: name, width, box sizes, price, the rules that apply.

    No room arithmetic (Senso can't check it; fit/ does). Box sizes come from data/products.json by product_id
    because Item has no packages_in."""
    name = item.get("name") or item.get("product_id") or "This item"
    slot = item.get("slot") or ""
    dims = item.get("dims_in") or {}
    parts: list[str] = []
    if dims.get("w") is not None:
        if slot == "rug" and dims.get("d") is not None:
            parts.append(f"The {name} is {_n(dims['w'])} inches wide and {_n(dims['d'])} inches long.")
        else:
            parts.append(f"The {name} is {_n(dims['w'])} inches wide.")
    p = _product(item.get("product_id") or "") or {}
    boxes = p.get("packages_in") or []
    if boxes:
        sizes = "; ".join(f"{_n(b['w'])} x {_n(b['d'])} x {_n(b['h'])} inches" for b in boxes
                          if None not in (b.get("w"), b.get("d"), b.get("h")))
        if sizes:
            parts.append(f"It ships in {len(boxes)} box{'es' if len(boxes) > 1 else ''}: {sizes}.")
    price = item.get("price_usd")
    if price is not None:
        parts.append(f"It costs ${_n(price)}.")
    if slot == "rug":
        parts.append(RULE_RUG)
    else:
        parts.append(RULE_WALKWAY)
    parts.append(RULE_DOORWAY)
    if slot == "sofa":
        parts.append(RULE_SOFA_WALL)
    return " ".join(parts)


def verdict_ok(check: dict | None) -> bool:
    """True when no claim is a conflict and at least one claim is verified."""
    if not check:
        return False
    verdicts = [c.get("verdict") for c in check.get("claims") or []]
    return "conflict" not in verdicts and "verified" in verdicts
