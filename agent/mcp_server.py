"""MCP server for Room Furnisher: lets anyone's own Claude (Claude Code, Claude Desktop, claude.ai) drive the tools.

The same tool functions back the web app (agent.agent -> claude -p -> this server) and a person's own Claude.
The tools enforce the rules (fit, Senso check before cart, audit records); this file only exposes them.

Tools: create_plan (new plan; a Claude user starts with nothing) + the 8 in agent.tools.TOOL_SPECS.
Every result carries plan_url and the line "Open your room: <plan_url>" so the person can open the live 3D page.

Run:
  python -m agent.mcp_server                      # stdio (Claude Code / Claude Desktop)
  python -m agent.mcp_server --http --port 8765   # streamable HTTP at http://127.0.0.1:8765/mcp
  python -m agent.mcp_server --http --host 0.0.0.0 --port 8765   # behind an HTTPS proxy for claude.ai
"""
from __future__ import annotations

import argparse
import json
import logging
from typing import Any

import anyio
import mcp_types as types
from mcp.server import Server

from agent import store, tools
from agent.types import audit

log = logging.getLogger("room_furnisher.mcp")

SERVER_NAME = "room_furnisher"

INSTRUCTIONS = (
    "Room Furnisher furnishes one living room from a real IKEA catalog and keeps an audit trail. "
    "Start with create_plan, then analyze_room (room photo and/or style words, exact inches if the person "
    "measured). If the person mentions a budget, call set_budget (or pass it to create_plan) before picking: the "
    "tools enforce it. With a total budget, split it across the slots first (sofa the biggest share) and pass each "
    "slot's share to pick as budget_usd, so an early pick doesn't use it all. For each slot (sofa, armchair, coffee_table, rug, floor_lamp): pick, senso_check, then cart_add "
    "with a one- or two-sentence why. Use swap if the person dislikes a pick. Nothing is ever purchased. "
    "Always give the person the plan_url so they can open their room in 3D."
)

CREATE_PLAN_SPEC = {
    "name": "create_plan",
    "description": "Start a new room plan. Call this first; every other tool needs its plan_id. Returns plan_id "
                   "and plan_url (the live 3D room page with the audit trail).",
    "input_schema": {"type": "object", "properties": {
        "total_usd": {"type": ["number", "null"], "description": "The person's budget for the whole room, if given."},
        "per_item_usd": {"type": ["number", "null"], "description": "The person's max price per item, if given."}},
        "additionalProperties": False},
}


def create_plan(total_usd: float | None = None, per_item_usd: float | None = None) -> dict:
    """Create an empty plan in the shared store and record where it came from; store a budget if given."""
    plan = store.new_plan()
    store.append_audit(plan["plan_id"], audit(
        "agent", source={"kind": "template"}, decision="plan created",
        why="New plan started from an MCP client (the person's own Claude)."))
    budget = None
    if total_usd is not None or per_item_usd is not None:
        res = tools.set_budget(plan["plan_id"], total_usd=total_usd, per_item_usd=per_item_usd)
        if not res.get("ok"):
            return res
        budget = res["budget"]
    return {"plan_id": plan["plan_id"], "plan_url": plan["plan_url"], "room": None, "style": None,
            "items": [], "cart": plan["cart"], "budget": budget}


def tool_specs() -> list[dict]:
    return [CREATE_PLAN_SPEC, *tools.TOOL_SPECS]


def _list_tools() -> list[types.Tool]:
    return [types.Tool(name=s["name"], description=s["description"], input_schema=s["input_schema"])
            for s in tool_specs()]


def _resolve(name: str):
    """Look the function up at call time (so tests can patch agent.tools.<name>)."""
    if name == "create_plan":
        return create_plan
    if name not in {s["name"] for s in tools.TOOL_SPECS}:
        return None
    return getattr(tools, name)


def _with_link(result: dict, plan_id: str | None) -> dict:
    out = dict(result)
    pid = out.get("plan_id") or plan_id
    if pid and not out.get("plan_url"):
        try:
            out["plan_url"] = store.plan_url(pid)
        except Exception:  # noqa: BLE001 - a bad id still gets a readable error, just no link
            pass
    if pid:
        out.setdefault("plan_id", pid)
    if out.get("plan_url"):
        out["open_your_room"] = f"Open your room: {out['plan_url']}"
    return out


def _to_result(payload: dict, is_error: bool = False) -> types.CallToolResult:
    lines = [payload["open_your_room"]] if payload.get("open_your_room") else []
    lines.append(json.dumps(payload, ensure_ascii=False, default=str))
    return types.CallToolResult(content=[types.TextContent(text="\n".join(lines))],
                                structured_content=payload, is_error=is_error)


def call(name: str, arguments: dict | None) -> types.CallToolResult:
    """Run one tool synchronously and wrap its dict as an MCP result. Errors come back as is_error results."""
    args = dict(arguments or {})
    fn = _resolve(name)
    if fn is None:
        return _to_result({"ok": False, "error": f"unknown tool {name!r}"}, is_error=True)
    plan_id = args.get("plan_id")
    try:
        result = fn(**args)
    except NotImplementedError:
        return _to_result(_with_link({"ok": False, "error": f"{name} is not implemented yet"}, plan_id), True)
    except (ValueError, KeyError, TypeError) as e:
        msg = f"unknown plan {e.args[0]!r}; call create_plan first" if isinstance(e, KeyError) else str(e)
        return _to_result(_with_link({"ok": False, "error": msg}, plan_id), True)
    except Exception as e:  # noqa: BLE001 - report to the model instead of killing the session
        log.exception("tool %s failed", name)
        return _to_result(_with_link({"ok": False, "error": f"{type(e).__name__}: {e}"}, plan_id), True)
    if not isinstance(result, dict):
        result = {"result": result}
    # Rule refusals ({"ok": False}) are normal results: the model reads why and recovers.
    return _to_result(_with_link(result, plan_id))


async def _on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=_list_tools())


async def _on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    # Tools are blocking (Superlinked, Senso ~7 s); keep the event loop free.
    return await anyio.to_thread.run_sync(call, params.name, params.arguments)


def build_server() -> Server:
    return Server(SERVER_NAME, version="0.1.0", instructions=INSTRUCTIONS,
                  on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)


async def _run_stdio(server: Server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Room Furnisher MCP server")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP at /mcp instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # stderr; stdout belongs to the stdio transport
    server = build_server()
    if not a.http:
        anyio.run(_run_stdio, server)
        return
    import uvicorn
    app = server.streamable_http_app(host=a.host)
    log.info("Room Furnisher MCP at http://%s:%d/mcp", a.host, a.port)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
