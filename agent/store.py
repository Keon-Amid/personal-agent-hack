"""Plan store shared across processes (FastAPI, the MCP server and tests all see the same plans).

One JSON file per plan under ~/.cache/room-furnisher/plans/ (override with ROOM_FURNISHER_PLANS_DIR).
Writes are atomic (temp file + os.replace) and serialized with an flock on a per-plan lock file, so a
read-modify-write in `update` cannot lose another process's audit record.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .types import DELIVERY_NOTE, now_ts

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def plans_dir() -> Path:
    d = Path(os.environ.get("ROOM_FURNISHER_PLANS_DIR") or Path.home() / ".cache" / "room-furnisher" / "plans")
    d.mkdir(parents=True, exist_ok=True)
    return d


def plan_url(plan_id: str) -> str:
    base = (os.environ.get("PUBLIC_BASE_URL") or "http://localhost:5173").rstrip("/")
    return f"{base}/plan/{plan_id}"


def _path(plan_id: str) -> Path:
    if not _ID.match(plan_id or ""):
        raise ValueError(f"bad plan_id {plan_id!r}")
    return plans_dir() / f"{plan_id}.json"


@contextmanager
def _locked(plan_id: str) -> Iterator[None]:
    lock = _path(plan_id).with_suffix(".lock")
    with open(lock, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _write(plan: dict) -> None:
    p = _path(plan["plan_id"])
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _stamp(plan: dict) -> dict:
    for rec in plan.get("audit", []):
        rec.setdefault("ts", now_ts())
    return plan


def new_plan(room: dict | None = None, style: dict | None = None, plan_id: str | None = None) -> dict:
    """Create and save an empty plan. room/style may be filled in later by analyze_room."""
    pid = plan_id or uuid.uuid4().hex[:12]
    plan = {
        "plan_id": pid, "plan_url": plan_url(pid), "room": room, "style": style, "items": [],
        "cart": {"items": [], "total_usd": 0.0, "delivery_note": DELIVERY_NOTE, "no_purchase": True},
        "audit": [], "state": {},
    }
    with _locked(pid):
        if _path(pid).exists():
            raise FileExistsError(f"plan {pid} exists")
        _write(plan)
    return plan


def get(plan_id: str) -> dict:
    """Load a plan. Raises KeyError if it doesn't exist."""
    p = _path(plan_id)
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        raise KeyError(plan_id) from None


def save(plan: dict) -> dict:
    """Overwrite the whole plan (ts stamped on any audit record missing one). Prefer `update` for edits."""
    _stamp(plan)
    with _locked(plan["plan_id"]):
        _write(plan)
    return plan


def update(plan_id: str, fn: Callable[[dict], object]) -> dict:
    """Locked read-modify-write: fn mutates the plan in place; the result is stamped and saved."""
    with _locked(plan_id):
        plan = get(plan_id)
        fn(plan)
        _stamp(plan)
        _write(plan)
    return plan


def append_audit(plan_id: str, record: dict) -> dict:
    """Append one audit record (ts stamped if missing). Returns the stored record."""
    rec = dict(record)
    rec.setdefault("ts", now_ts())
    update(plan_id, lambda plan: plan.setdefault("audit", []).append(rec))
    return rec
