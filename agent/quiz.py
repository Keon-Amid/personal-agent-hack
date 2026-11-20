"""Persona quiz -> run_agent inputs.

`score(answers)` turns the 5 answers in agent/quiz.json into `style_text` and `budget_usd` for
`agent.agent.run_agent`, plus a `trace` that shows every answer's effect (for the audit panel).
A quiz style_text overrides the style detected from the room photo (see data/sie.analyze_room).
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.types import SLOTS

HERE = Path(__file__).parent
QUIZ = json.loads((HERE / "quiz.json").read_text())
PRODUCTS = HERE.parent / "data" / "products.json"
EMB = HERE.parent / "data" / "style_embeddings.json"
MUTE_BELOW = 0.05  # CONTRACT (alistair): product_styles scores under 0.05 are weak; cards mute them


def _option(qid: str, oid: str) -> dict:
    for q in QUIZ["questions"]:
        if q["id"] == qid:
            for o in q["options"]:
                if o["id"] == oid:
                    return o
            raise ValueError(f"{qid}: unknown option {oid!r}")
    raise ValueError(f"unknown question {qid!r}")


def score(answers: dict[str, str]) -> dict:
    """answers: {question_id: option_id} for all 5 questions."""
    missing = [q["id"] for q in QUIZ["questions"] if q["id"] not in answers]
    if missing:
        raise ValueError(f"unanswered: {missing}")
    scores = {s: 0 for s in QUIZ["styles"]}
    words, trace, budget = [], [], None
    for q in QUIZ["questions"]:
        o = _option(q["id"], answers[q["id"]])
        for s, w in o.get("weights", {}).items():
            scores[s] += w
        if o.get("style_words"):
            words.append(o["style_words"])
        if "budget_usd" in o:
            budget = o["budget_usd"]
        trace.append({"question": q["id"], "answer": o["id"], "label": o["label"],
                      "weights": o.get("weights", {}), "style_words": o.get("style_words"),
                      "ref_url": o.get("ref_url")})
    # Ties break by STYLES order, so the same answers always give the same style.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], QUIZ["styles"].index(kv[0])))
    style = ranked[0][0]
    style_text = f"{style} living room, " + ", ".join(words)
    return {"style": style, "style_scores": dict(ranked), "style_text": style_text,
            "budget_usd": budget, "trace": trace}


def catalog_support(style: str, products_path: Path = PRODUCTS, emb_path: Path = EMB) -> dict:
    """Which catalog products Superlinked labels with the quiz style, per agent slot.

    Reads alistair's product_styles (zero-shot SigLIP labels on each product photo, top 3 per product) from
    data/style_embeddings.json. No API call. A slot with no labelled product still gets a pick: style_match
    ranks relatively. This only tells the person, honestly, how well the catalog covers their style.
    """
    products = {p["id"]: p for p in json.loads(products_path.read_text())["products"]}
    labels = json.loads(emb_path.read_text()).get("product_styles") or {}
    slots = {}
    for slot in SLOTS:
        hits = [{"id": pid, "name": products[pid]["name"], "score": s["score"]}
                for pid, styles in labels.items() if pid in products and products[pid]["category"] == slot
                for s in styles if s["style"] == style and s["score"] >= MUTE_BELOW]
        slots[slot] = sorted(hits, key=lambda h: -h["score"])
    covered = [s for s, h in slots.items() if h]
    return {"style": style, "source": {"kind": "superlinked", "field": "product_styles", "min_score": MUTE_BELOW},
            "slots": slots, "covered": covered,
            "summary": f"{len(covered)} of {len(SLOTS)} slots have a product Superlinked labels {style}"}
