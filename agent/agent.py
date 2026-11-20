"""Run the furnishing agent on Claude Code headless (brendan's Claude subscription, no Anthropic API key).

run_agent creates the plan, runs analyze_room here, then spawns `claude -p` with our MCP server as the ONLY tool
source. The model chooses the order and writes the explanations; the tools (agent.tools, via agent.mcp_server in
Claude Code's child process) enforce the rules and write their own audit records to the shared plan store.
This module adds one audit record (step "agent", source claude/claude_code) per tool call and per piece of
assistant text it sees in the stream, and passes each to on_event.

For the demo on brendan's own machine only: it uses whoever is signed in to `claude` locally.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from . import store, tools
from .types import audit

REPO = Path(__file__).resolve().parent.parent
MCP_JSON = Path(__file__).resolve().parent / "mcp.json"
PROMPT = Path(__file__).resolve().parent / "prompts" / "furnish.md"
SERVER = "room_furnisher"
TOOL_PREFIX = f"mcp__{SERVER}__"
ALLOWED_TOOLS = f"{TOOL_PREFIX}*"
TIMEOUT_S = 240
SIGN_IN_FIX = "run `claude` in a terminal and sign in with the Claude subscription (or `claude auth login`)"
# Never let an API key reach the child: the subscription must be used.
_STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_EXACT_KEYS = ("wall", "depth", "door_width", "door_height")


class AgentError(RuntimeError):
    """The agent could not run or finished with an error. plan_id is set once a plan exists."""

    def __init__(self, msg: str, plan_id: str | None = None):
        super().__init__(msg)
        self.plan_id = plan_id


class AgentTimeout(AgentError):
    pass


def child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def mcp_config() -> dict:
    """agent/mcp.json with paths pointed at this checkout (so worktrees and the main repo both work)."""
    cfg = json.loads(MCP_JSON.read_text())
    srv = cfg["mcpServers"][SERVER]
    venv_py = REPO / ".venv" / "bin" / "python"
    if not Path(srv["command"]).exists():
        srv["command"] = str(venv_py if venv_py.exists() else Path(sys.executable))
    env = dict(srv.get("env") or {})
    env["PYTHONPATH"] = str(REPO)
    for k in ("ROOM_FURNISHER_PLANS_DIR", "PUBLIC_BASE_URL"):  # the server must see the same plan store
        if os.environ.get(k):
            env[k] = os.environ[k]
    srv["env"] = env
    return cfg


def build_prompt(plan_id: str, budget_usd: float | None, budget_total_usd: float | None = None) -> str:
    text = PROMPT.read_text().replace("{{plan_id}}", plan_id)
    lines = []
    if budget_usd is not None:
        b = f"{float(budget_usd):g}"
        lines.append(f"The person's budget is ${b} per item: pass budget_usd={b} to every pick.")
    if budget_total_usd is not None:
        t = f"{float(budget_total_usd):g}"
        lines.append(f"The person's total budget is ${t} for the whole room. Split it across the five slots before "
                     f"picking (a sofa needs the biggest share, a lamp the smallest) and pass each slot's share as "
                     f"budget_usd, so a big early pick doesn't leave nothing for the rest.")
    if lines:
        lines.append("The tools enforce the budget: pick never returns a pricier item and cart_add refuses one.")
        text = text.replace("{{budget_line}}", " ".join(lines))
        text = text.replace("{{budget_arg}}", ", budget_usd=<that slot's share>" if budget_total_usd is not None
                            and budget_usd is None else f", budget_usd={float(budget_usd):g}" if budget_usd is not None else "")
    else:
        text = text.replace("{{budget_line}}", "No budget was given: call pick without budget_usd.")
        text = text.replace("{{budget_arg}}", "")
    return text


def build_command(prompt: str) -> list[str]:
    cmd = ["claude", "-p", prompt,
           "--mcp-config", json.dumps(mcp_config()), "--strict-mcp-config",
           "--output-format", "stream-json", "--verbose",
           "--tools", "",                       # no built-in tools (no Bash/Read/Edit/WebFetch)
           "--allowedTools", ALLOWED_TOOLS,     # only our MCP tools, no prompts
           "--permission-mode", "dontAsk",      # anything else is denied, never asked
           "--no-session-persistence"]
    if os.environ.get("ROOM_FURNISHER_MODEL"):
        cmd += ["--model", os.environ["ROOM_FURNISHER_MODEL"]]
    return cmd


def check_claude() -> None:
    """Raise AgentError with the fix if `claude` is missing or not signed in."""
    if not shutil.which("claude"):
        raise AgentError("Claude Code (`claude`) is not on PATH. Install Claude Code, then " + SIGN_IN_FIX + ".")
    try:
        out = subprocess.run(["claude", "auth", "status", "--json"], capture_output=True, text=True,
                             timeout=20, env=child_env())
    except subprocess.TimeoutExpired:
        raise AgentError("`claude auth status` timed out; " + SIGN_IN_FIX + ".") from None
    try:
        status = json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        status = {}
    if not status.get("loggedIn"):
        raise AgentError("Claude Code is not signed in: " + SIGN_IN_FIX + ".")


def _exact(room_input: dict | None) -> dict | None:
    """Exact inches the person typed. Accepts {"wall": 88} or fit.measurement dicts with source "user"."""
    out = {}
    for k in _EXACT_KEYS:
        v = (room_input or {}).get(k)
        if isinstance(v, dict):
            v = v.get("value_in") if v.get("source", "user") == "user" else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = float(v)
    return out or None


def _short(v, n: int = 300) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def _records_for(event: dict, calls: dict) -> list[dict]:
    """Audit records for one stream-json event: a tool call, assistant text, or a failed tool result."""
    src = {"kind": "claude", "via": "claude_code"}
    recs = []
    et = event.get("type")
    msg = event.get("message") or {}
    if et == "assistant":
        if msg.get("model"):
            src = {**src, "model": msg["model"]}
        for block in msg.get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                recs.append(audit("agent", source=src, decision="said", why=block["text"].strip()))
            elif block.get("type") == "tool_use":
                name = block.get("name", "")
                short = name[len(TOOL_PREFIX):] if name.startswith(TOOL_PREFIX) else name
                inp = block.get("input") or {}
                calls[block.get("id")] = short
                rec = audit("agent", source=src, decision=f"call {short}", input=inp,
                            why=f"The model chose to call {short}" + (f" for {inp['slot']}" if inp.get("slot") else ""),
                            status="called")
                if inp.get("slot"):
                    rec["item_slot"] = inp["slot"]
                recs.append(rec)
    elif et == "user":
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result" and block.get("is_error"):
                short = calls.get(block.get("tool_use_id"), "tool")
                recs.append(audit("agent", source={"kind": "template"}, decision=f"{short} failed",
                                  why=_short(block.get("content")), status="error"))
    return recs


def run_agent(room_input: dict, photo_b64: str | None = None, style_text: str | None = None,
              budget_usd: float | None = None, on_event: Callable[[dict], None] | None = None,
              budget_total_usd: float | None = None,
              plan_id: str | None = None) -> dict:
    """Furnish a room end to end and return the Plan (agent.tools.get_plan).

    room_input: exact inches the person measured, {"wall", "depth", "door_width", "door_height"} (any subset;
    numbers, or fit.measurement dicts with source "user"). Missing keys are estimated from the photo by
    analyze_room. Raises AgentError (with .plan_id once the plan exists) or AgentTimeout after TIMEOUT_S.
    plan_id: use this id for the new plan (the web server hands it to the browser before the run starts).
    """
    check_claude()
    plan = store.new_plan(plan_id=plan_id)
    pid = plan["plan_id"]

    def emit(rec: dict) -> None:
        store.append_audit(pid, rec)
        if on_event:
            try:
                on_event(rec)
            except Exception:  # a broken listener must not kill the run
                pass

    if budget_usd is not None or budget_total_usd is not None:  # enforced by the tools, not just the prompt
        tools.set_budget(pid, total_usd=budget_total_usd, per_item_usd=budget_usd)
    tools.analyze_room(pid, photo_b64=photo_b64, style_text=style_text, exact=_exact(room_input))

    cmd = build_command(build_prompt(pid, budget_usd, budget_total_usd))
    emit(audit("agent", source={"kind": "template"}, decision="start Claude Code agent",
               input={"tools": ALLOWED_TOOLS, "budget_usd": budget_usd},
               why="Headless Claude Code with only the room_furnisher tools; the tools enforce fit and Senso checks.",
               status="started"))

    stderr = tempfile.TemporaryFile(mode="w+")
    try:
        proc = subprocess.Popen(cmd, cwd=str(REPO), env=child_env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=stderr, text=True, bufsize=1)
    except FileNotFoundError:
        raise AgentError("Claude Code (`claude`) is not on PATH: " + SIGN_IN_FIX + ".", pid) from None

    lines: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + TIMEOUT_S
    calls: dict = {}
    result: dict | None = None
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise queue.Empty
            line = lines.get(timeout=left)
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                for s in event.get("mcp_servers") or []:
                    if s.get("name") == SERVER and s.get("status") in ("failed", "needs-auth"):
                        raise AgentError(f"MCP server {SERVER} did not start (status {s.get('status')}).", pid)
            if event.get("type") == "result":
                result = event
            for rec in _records_for(event, calls):
                emit(rec)
        proc.wait(timeout=max(1.0, deadline - time.monotonic()))
    except (queue.Empty, subprocess.TimeoutExpired):
        proc.kill()
        proc.wait()
        emit(audit("agent", source={"kind": "template"}, decision="stopped: timeout",
                   why=f"Claude Code ran longer than {TIMEOUT_S} s and was stopped.", status="timeout"))
        raise AgentTimeout(f"agent timed out after {TIMEOUT_S} s (plan {pid})", pid) from None
    except AgentError:
        proc.kill()
        proc.wait()
        raise
    finally:
        stderr.seek(0)
        err_tail = stderr.read()[-1000:]
        stderr.close()

    failed = proc.returncode != 0 or result is None or result.get("is_error")
    if failed:
        detail = (result or {}).get("result") or err_tail.strip() or f"exit code {proc.returncode}"
        hint = ""
        low = detail.lower()
        if any(w in low for w in ("log in", "login", "not logged", "authenticat", "api key")):
            hint = " Fix: " + SIGN_IN_FIX + "."
        emit(audit("agent", source={"kind": "template"}, decision="agent failed", why=_short(detail, 500),
                   status="error"))
        raise AgentError(f"Claude Code agent failed: {_short(detail, 500)}{hint}", pid)

    emit(audit("agent", source={"kind": "template"}, decision="agent finished",
               input={"num_turns": result.get("num_turns"), "duration_ms": result.get("duration_ms")},
               why="Claude Code finished; see the tool records above for every decision.", status="done"))
    if os.environ.get("ARCEE_WHY_MODEL"):  # optional sponsor step: Arcee writes an alternative why per item
        try:
            from . import arcee
            arcee.add_arcee_whys(pid, os.environ["ARCEE_WHY_MODEL"])  # audits itself; Claude's why stays default
        except Exception as e:  # noqa: BLE001 - never fail a finished run over the optional step
            emit(audit("agent", source={"kind": "arcee"}, decision="arcee step failed", status="error",
                       why=f"{type(e).__name__}: {e}"))
    return tools.get_plan(pid)
