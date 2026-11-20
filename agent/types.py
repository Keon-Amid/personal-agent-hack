"""Shared shapes for the agent lane. contracts/plan.example.json is a filled-in example of a Plan.

TypedDicts are documentation plus editor help; at runtime a Plan is a plain JSON-serializable dict.
"""

from datetime import datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

SLOTS = ("sofa", "armchair", "coffee_table", "rug", "floor_lamp")
STEPS = ("estimate_room", "rank", "pick", "senso_check", "swap", "cart", "agent")
SOURCE_KINDS = ("photo", "catalog", "fit", "superlinked", "senso", "claude", "template")
DELIVERY_NOTE = "IKEA home delivery from $29"

Step = Literal["estimate_room", "rank", "pick", "senso_check", "swap", "cart", "agent"]
SourceKind = Literal["photo", "catalog", "fit", "superlinked", "senso", "claude", "template"]
Verdict = Literal["verified", "conflict", "unsupported", "not_verifiable"]


class Measurement(TypedDict):
    """fit.measurement(...) output."""
    value_in: float
    error_in: float
    source: str  # "user" | "estimated:door" | "estimated:paper"


class Room(TypedDict):
    wall: Measurement
    depth: Measurement
    door_width: Measurement
    door_height: Measurement
    photo_url: NotRequired[str | None]


class Style(TypedDict):
    style_text: str | None
    detected_style: str | None


class Source(TypedDict, total=False):
    kind: SourceKind  # always present; other keys depend on the kind (url, check_id, model, ...)


class AuditRecord(TypedDict):
    ts: str
    step: Step
    source: Source
    decision: str
    why: str
    item_slot: NotRequired[str]
    product_id: NotRequired[str]
    input: NotRequired[Any]
    status: NotRequired[str]


class SensoClaim(TypedDict):
    claim: str
    verdict: Verdict
    quote: str | None


class SensoCheck(TypedDict):
    check_id: str
    accuracy_pct: float | None
    claims: list[SensoClaim]


class ItemStyle(TypedDict):
    rank: int
    fused: float | None
    photo_score: float | None
    text_score: float | None
    product_styles: list[str]


class ItemFit(TypedDict):
    verdict: Literal["fits", "unsure", "no_fit"]
    results: list[dict]


class Rejected(TypedDict):
    product_id: str
    name: str
    status: str  # no_fit | unsure | rejected | swapped_out
    why: str


class WhySource(TypedDict):
    kind: Literal["claude", "template"]


class Item(TypedDict):
    slot: str
    product_id: str
    name: str
    price_usd: float | None
    dims_in: dict
    image_url: str | None
    source_url: str
    style: ItemStyle
    fit: ItemFit
    senso: SensoCheck | None
    why: str
    why_source: WhySource
    rejected: list[Rejected]


class CartItem(TypedDict):
    product_id: str
    name: str
    price_usd: float | None
    source_url: str


class Cart(TypedDict):
    items: list[CartItem]
    total_usd: float
    delivery_note: str
    no_purchase: bool  # always True: we build a cart, we never buy


class Plan(TypedDict):
    plan_id: str
    plan_url: str
    room: Room | None
    style: Style | None
    items: list[Item]
    cart: Cart
    audit: list[AuditRecord]
    fixture: NotRequired[bool]
    state: NotRequired[dict]  # tool-private JSON state (room vector, style_match results, swap history)


def now_ts() -> str:
    """UTC timestamp, ISO 8601 with Z, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(step: str, **f: Any) -> dict:
    """One AuditRecord with ts stamped. `source` defaults to {"kind": "template"}; decision/why default to ""."""
    if step not in STEPS:
        raise ValueError(f"unknown audit step {step!r}")
    rec = {"ts": now_ts(), "step": step, "source": {"kind": "template"}, "decision": "", "why": ""}
    rec.update(f)
    return rec
