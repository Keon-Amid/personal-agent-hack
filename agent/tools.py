"""The agent's tools: the contract shared by the FastAPI path (agent.agent) and the MCP server (agent.mcp_server).

The tools enforce the rules; the model only chooses the order and explains.
- pick only returns items that fit (fit.pick walks the Superlinked style ranking and skips no_fit/unsure).
- cart_add refuses any item whose Senso check has a conflict or no verified claim.
- every tool appends its own AuditRecord to the plan (agent.store), so a model can't skip a check or invent a fit.

Every tool takes plain JSON values and returns a JSON-serializable dict that includes plan_id and plan_url.
On a rule violation a tool returns {"ok": False, "error": ..., plan_id, plan_url} (and audits the refusal)
rather than raising, so the model can read why and recover. Unknown plan_id / slot raises ValueError.

A1 status: STUBS. Bodies land in A5/A6; signatures and docstrings here are the contract.
"""
from __future__ import annotations

SLOT_ENUM = ["sofa", "armchair", "coffee_table", "rug", "floor_lamp"]


def analyze_room(plan_id: str, photo_b64: str | None = None, style_text: str | None = None,
                 exact: dict | None = None) -> dict:
    """Set the room's measurements and style on the plan.

    photo_b64: base64 room photo; used for Superlinked room-style detection (data.sie.analyze_room) and, when
        no exact numbers are given, for estimated measurements (source "estimated:door"/"estimated:paper",
        with error_in > 0, so wide items may come back "unsure").
    style_text: the person's words for the style ("warm minimal, light oak"); used if no photo, or fused with it.
    exact: measurements the person typed, in inches: {"wall", "depth", "door_width", "door_height"};
        stored as fit.measurement(v, 0, "user"). Exact values override estimates key by key.
    The Superlinked room vector is stored in plan["state"] so later style_match calls make no new room call.
    Audits step "estimate_room" (source photo/template) and the style detection (source superlinked).
    Returns {plan_id, plan_url, room, style}.
    """
    raise NotImplementedError


def style_match(plan_id: str, slot: str) -> dict:
    """Rank the catalog products for one slot by style against the room (data.sie.style_match).

    Uses the room analysis stored by analyze_room; caches the result in plan["state"]["style"][slot].
    Audits step "rank" (source superlinked).
    Returns {plan_id, plan_url, slot, style_text, detected_style, ranked: [{product_id, name, style_rank,
    photo_rank, photo_score, text_rank, text_score, product_styles}]}.
    """
    raise NotImplementedError


def fit_options(plan_id: str, slot: str) -> dict:
    """Fit every catalog product for one slot against the plan's room (fit.options.options).

    Audits step "rank" (source fit) with counts of fits/unsure/no_fit.
    Returns {plan_id, plan_url, slot, options: [{product_id, name, price_usd, rating, review_count,
    fit, fit_results (each with its math), best_value, why}]}.
    """
    raise NotImplementedError


def pick(plan_id: str, slot: str, budget_usd: float | None = None) -> dict:
    """Pick the best style match that fits (and is within budget) for one slot (fit.pick.pick).

    Runs style_match / fit_options first if they haven't run for this slot. Writes the Item to plan["items"]
    (replacing any earlier pick for the slot) with why_source template until the agent explains in cart_add.
    Appends fit.pick's audit records (ts stamped). Never returns an item whose fit is not "fits".
    Returns {plan_id, plan_url, slot, picked: Item | None, rejected: [{product_id, name, status, why}]}.
    picked is None (with the reasons in rejected) when nothing fits.
    """
    raise NotImplementedError


def senso_check(plan_id: str, slot: str) -> dict:
    """Fact-check the picked item for one slot against the Senso knowledge base.

    Builds the claim text from the item's catalog facts (name, price, dims) and the clearance rule it relies
    on (walkway, wall fit, doorway boxes, rug margin), posts it to Senso /org/evals/text, and stores
    item["senso"] = {check_id, accuracy_pct, claims: [{claim, verdict, quote}]}.
    Only "conflict" blocks the item; "unsupported" on room numbers is expected (fit/ decides fit).
    Audits step "senso_check" (source senso, check_id).
    Returns {plan_id, plan_url, slot, product_id, senso, ok: no conflict and >= 1 verified}.
    """
    raise NotImplementedError


def swap(plan_id: str, slot: str) -> dict:
    """Replace the slot's pick with the next fitting style match, excluding every product picked before.

    Uses the cached style_match (no new Superlinked call) and fit.pick.pick(exclude=...). Clears the slot's
    Senso check and removes it from the cart. Audits step "swap".
    Returns the same shape as pick, plus {"excluded": [product_id, ...]}.
    """
    raise NotImplementedError


def cart_add(plan_id: str, slot: str, why: str) -> dict:
    """Add the slot's picked item to the cart (a cart, never a purchase: cart.no_purchase is always true).

    REFUSES (ok False, audited) unless the item's Senso check exists, has no "conflict" claim and has at
    least one "verified" claim. why = the agent's explanation for the person; stored on the item with
    why_source {"kind": "claude"} and in the audit record (step "cart", source claude).
    Returns {plan_id, plan_url, ok, slot, cart} or {plan_id, plan_url, ok: False, error}.
    """
    raise NotImplementedError


def get_plan(plan_id: str) -> dict:
    """Return the whole plan (room, style, items, cart, audit) without plan["state"]. Not audited."""
    raise NotImplementedError


_PLAN = {"plan_id": {"type": "string", "description": "The plan to work on."}}
_SLOT = {"slot": {"type": "string", "enum": SLOT_ENUM, "description": "Which piece of furniture."}}


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOL_SPECS: list[dict] = [
    {"name": "analyze_room",
     "description": "Set the room's measurements and style. Give a room photo (base64) and/or style words, and "
                    "exact measurements in inches if the person has them. Returns the room and detected style.",
     "input_schema": _schema({
         **_PLAN,
         "photo_b64": {"type": ["string", "null"], "description": "Base64 room photo."},
         "style_text": {"type": ["string", "null"], "description": "The person's style words."},
         "exact": {"type": ["object", "null"], "description": "Exact inches the person measured.",
                   "properties": {k: {"type": "number"} for k in ("wall", "depth", "door_width", "door_height")},
                   "additionalProperties": False},
     }, ["plan_id"])},
    {"name": "style_match",
     "description": "Rank the products for one slot by how well they match the room's style (Superlinked).",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "fit_options",
     "description": "Check every product for one slot against the room: wall, walkway, doorway. Shows the math "
                    "and which are best value.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "pick",
     "description": "Pick the best style match that fits the room (and budget) for one slot. Only fitting items "
                    "can be picked; the others come back with the reason they were rejected.",
     "input_schema": _schema({**_PLAN, **_SLOT,
                              "budget_usd": {"type": ["number", "null"], "description": "Max price for this item."}},
                             ["plan_id", "slot"])},
    {"name": "senso_check",
     "description": "Fact-check the picked item's specs, price and clearance rules against the Senso knowledge "
                    "base. Required before cart_add.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "swap",
     "description": "Replace the slot's pick with the next fitting style match, never repeating an earlier pick.",
     "input_schema": _schema({**_PLAN, **_SLOT}, ["plan_id", "slot"])},
    {"name": "cart_add",
     "description": "Add the slot's picked item to the cart (no purchase is made). Refused unless its Senso check "
                    "has a verified claim and no conflict. 'why' is your one- or two-sentence explanation for the "
                    "person.",
     "input_schema": _schema({**_PLAN, **_SLOT, "why": {"type": "string"}}, ["plan_id", "slot", "why"])},
    {"name": "get_plan",
     "description": "Get the whole plan: room, style, items, cart and audit trail.",
     "input_schema": _schema({**_PLAN}, ["plan_id"])},
]
