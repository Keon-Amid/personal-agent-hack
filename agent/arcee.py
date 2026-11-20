"""Arcee (sponsor): open-weight models write each pick's one-line "why" from the facts, with cost and latency.

Optional. Claude's why stays the default on every item; Arcee's lines go in item["why_alternatives"] and in the
audit trail (step "agent", source {"kind": "arcee", model, cost_usd, latency_ms, tokens}), so you can see which
model wrote what and what it cost.

    arcee_why(plan_id, slot, model=None)   # one item, one model; audited
    add_arcee_whys(plan_id, model=None)    # every item in a plan (run_agent calls this when ARCEE_WHY_MODEL is set)
    python3 -m agent.arcee pareto contracts/plan.live.json   # every model x every item -> contracts/arcee_pareto.json

The why is written ONLY from facts the tools produced (fit math, style rank, Senso verdicts, price, rejections).
Quality is scored without a judge model: grounded = every number in the sentence appears in the facts (no invented
numbers), plus whether it names the price and a fit fact. The pareto command keeps the models nobody beats on both
cost and quality. Stdlib only; needs ARCEE_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("ARCEE_API", "https://api.arcee.ai/api/v1")
DEFAULT_MODEL = os.environ.get("ARCEE_WHY_MODEL") or "zai-org/glm-5.3-flash"
UA = "Mozilla/5.0 personal-agent-hack"
SYSTEM = ("You write ONE sentence (max 30 words) telling a person why this piece of furniture was chosen for their "
          "room. Use only the facts given. Never invent a number, a measurement, a material or a claim. Mention the "
          "price and the most important fit fact. Plain words, no marketing.")


def _key() -> str:
    k = os.environ.get("ARCEE_API_KEY")
    env = ROOT / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ARCEE_API_KEY="):
                k = line.split("=", 1)[1].split("#")[0].strip().strip("\"'")
    if not k:
        raise RuntimeError("ARCEE_API_KEY is not set (put it in .env)")
    return k


def _http(path: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


@lru_cache(maxsize=1)
def models() -> dict:
    """{model_id: {"in": $/token, "out": $/token}} from Arcee's /models (prices as Arcee lists them)."""
    out = _http("/models")
    data = out.get("data", out) if isinstance(out, dict) else out
    return {m["id"]: {"in": float((m.get("pricing") or {}).get("prompt") or 0),
                      "out": float((m.get("pricing") or {}).get("completion") or 0)} for m in data}


def facts_for(item: dict) -> dict:
    """The facts the tools produced for this pick, and nothing else."""
    fit = item.get("fit") or {}
    results = fit.get("results") or []
    senso = item.get("senso") or {}
    claims = senso.get("claims") or []
    style = item.get("style") or {}
    return {
        "product": item.get("name"),
        "price_usd": item.get("price_usd"),
        "size_in": item.get("dims_in"),
        "fit_verdict": fit.get("verdict"),
        "fit_math": [r.get("math") for r in results if r.get("math")][:4],
        "style_rank": style.get("rank") or style.get("style_rank"),
        "senso": {"verified": sum(c.get("verdict") == "verified" for c in claims), "claims": len(claims)},
        "rejected": [f'{r.get("name") or r.get("product_id")}: {r.get("why")}' for r in (item.get("rejected") or [])][:3],
    }


_NUM = re.compile(r"\d+(?:\.\d+)?")


def score(text: str, facts: dict) -> dict:
    """Judge-free quality: no invented numbers (grounded), names the price, names a fit fact."""
    if not text.strip():
        return {"quality": 0.0, "grounded": False, "invented_numbers": [], "names_price": False,
                "names_fit": False, "empty": True}
    blob = json.dumps(facts)
    known = {float(n) for n in _NUM.findall(blob)}
    nums = [float(n) for n in _NUM.findall(text.replace(",", ""))]
    invented = [n for n in nums if not any(abs(n - k) < 0.01 for k in known)]
    price = facts.get("price_usd")
    has_price = price is not None and any(abs(n - price) < 0.01 for n in nums)
    has_fit = bool(re.search(r"\b(fit|fits|wall|door|walkway|clear|room)\b", text, re.I))
    q = (0.5 if not invented else 0.0) + (0.25 if has_price else 0) + (0.25 if has_fit else 0)
    return {"quality": q, "grounded": not invented, "invented_numbers": invented,
            "names_price": has_price, "names_fit": has_fit}


def write_why(facts: dict, model: str = DEFAULT_MODEL) -> dict:
    """One sentence from Arcee + measured latency, tokens and cost (Arcee's listed prices)."""
    t0 = time.monotonic()
    out = _http("/chat/completions", {
        "model": model, "temperature": 0, "max_tokens": 900,  # reasoning models think first
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": "Facts:\n" + json.dumps(facts, ensure_ascii=False)}]})
    ms = round((time.monotonic() - t0) * 1000)
    msg = out["choices"][0]["message"]
    text = (msg.get("content") or "").strip().strip('"')
    usage = out.get("usage") or {}
    tin, tout = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    price = models().get(model, {"in": 0, "out": 0})
    return {"text": text, "model": model, "latency_ms": ms, "input_tokens": tin, "output_tokens": tout,
            "reasoning_tokens": reasoning_tokens, "reasoning": (msg.get("reasoning_content") or "")[:400],
            "cost_usd": round(tin * price["in"] + tout * price["out"], 7)}


def arcee_why(plan_id: str, slot: str, model: str | None = None) -> dict:
    """Write Arcee's why for one picked item; keep Claude's why as the item's main why; audit model/cost/latency."""
    from . import tools
    from .types import audit
    model = model or DEFAULT_MODEL
    plan = tools._load(plan_id)
    item = tools._slot_item(plan, slot)
    if item is None:
        return {**tools._ids(plan), "ok": False, "error": f"nothing picked for {slot}"}
    facts = facts_for(item)
    try:
        res = write_why(facts, model)
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
        rec = audit("agent", item_slot=slot, product_id=item["product_id"], source={"kind": "arcee", "model": model},
                    decision="arcee why failed", status="error", why=f"{type(e).__name__}: {e}")
        tools._commit(plan_id, [rec])
        return {**tools._ids(plan), "ok": False, "error": str(e)}
    q = score(res["text"], facts)
    src = {"kind": "arcee", "model": model, "cost_usd": res["cost_usd"], "latency_ms": res["latency_ms"],
           "input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
           "reasoning_tokens": res["reasoning_tokens"], "reasoning": res["reasoning"], "grounded": q["grounded"]}
    rec = audit("agent", item_slot=slot, product_id=item["product_id"], source=src, decision="arcee wrote why",
                status="written", why=res["text"])

    def mutate(p: dict) -> None:
        it = tools._slot_item(p, slot)
        if it and it["product_id"] == item["product_id"]:
            alts = [a for a in it.get("why_alternatives", []) if a["source"].get("model") != model]
            it["why_alternatives"] = alts + [{"text": res["text"], "source": src}]

    plan = tools._commit(plan_id, [rec], mutate)
    return {**tools._ids(plan), "ok": True, "slot": slot, "why": res["text"], "source": src, "quality": q}


def add_arcee_whys(plan_id: str, model: str | None = None) -> list[dict]:
    from . import tools
    return [arcee_why(plan_id, it["slot"], model) for it in tools._load(plan_id).get("items", [])]


def pareto(plan_path: str | Path, model_ids: list[str] | None = None) -> dict:
    """Every model writes a why for every item of a saved plan; cost, latency and quality per model; the frontier."""
    plan = json.loads(Path(plan_path).read_text())
    ids = model_ids or sorted(models(), key=lambda m: models()[m]["out"])
    rows = []
    for m in ids:
        per = []
        for it in plan.get("items", []):
            f = facts_for(it)
            try:
                r = write_why(f, m)
            except Exception as e:  # noqa: BLE001 - a model that errors is reported, not fatal
                per.append({"slot": it["slot"], "error": f"{type(e).__name__}: {e}"})
                continue
            per.append({"slot": it["slot"], "text": r["text"], **{k: r[k] for k in
                        ("latency_ms", "input_tokens", "output_tokens", "reasoning_tokens", "cost_usd")}, **score(r["text"], f)})
        ok = [p for p in per if "error" not in p]
        rows.append({"model": m, "items": per,
                     "cost_usd_per_item": round(sum(p["cost_usd"] for p in ok) / len(ok), 7) if ok else None,
                     "latency_ms_avg": round(sum(p["latency_ms"] for p in ok) / len(ok)) if ok else None,
                     "quality_avg": round(sum(p["quality"] for p in ok) / len(ok), 3) if ok else 0.0,
                     "grounded_rate": round(sum(p["grounded"] for p in ok) / len(ok), 3) if ok else 0.0,
                     "errors": len(per) - len(ok)})
    good = [r for r in rows if r["cost_usd_per_item"] is not None]
    for r in good:
        r["on_frontier"] = not any(o is not r and o["cost_usd_per_item"] <= r["cost_usd_per_item"]
                                   and o["quality_avg"] >= r["quality_avg"]
                                   and (o["cost_usd_per_item"], -o["quality_avg"]) != (r["cost_usd_per_item"], -r["quality_avg"])
                                   for o in good)
    claude = [{"slot": it["slot"], "text": it.get("why"), **score(it.get("why") or "", facts_for(it))}
              for it in plan.get("items", []) if (it.get("why_source") or {}).get("kind") == "claude"]
    return {"plan": str(plan_path), "prices": "Arcee /models list prices, $ per token", "models": rows,
            "claude_baseline": {"items": claude,
                                "quality_avg": round(sum(c["quality"] for c in claude) / len(claude), 3) if claude else None}}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["pareto"] and len(a) > 1:
        res = pareto(a[1], a[2].split(",") if len(a) > 2 else None)
        out = ROOT / "contracts" / "arcee_pareto.json"
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        for r in res["models"]:
            print(f'{r["model"]:38} ${r["cost_usd_per_item"]}/item  {r["latency_ms_avg"]} ms  quality {r["quality_avg"]}'
                  f'  grounded {r["grounded_rate"]}  {"FRONTIER" if r.get("on_frontier") else ""}  errors {r["errors"]}')
        print("claude baseline quality:", res["claude_baseline"]["quality_avg"], "->", out.relative_to(ROOT))
    else:
        print(__doc__)
