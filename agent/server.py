"""HTTP API for the web app (keon's live mode). Standard library only, no new dependency.

    python -m agent.server [--port 8000]

POST /api/plan  {room: {wall, depth, door_width, door_height}, style_text, budget_usd, scan_path?, scan_wall?}
                -> 202 {plan_id, plan_url}; the agent runs in a background thread (claude -p + our MCP tools).
GET  /api/plan/{id} -> the Plan (contracts/plan.live.json shape), with items[] and audit[] growing while it runs,
                plus "status": running | done | error and "error" when it failed. Poll it (keon: every second).
GET  /api/health -> {ok: true}
CORS: http://localhost:5173 by default (WEB_ORIGIN to change).
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import store

ORIGIN = os.environ.get("WEB_ORIGIN", "http://localhost:5173")
_status: dict[str, dict] = {}  # plan_id -> {"status", "error"} for runs started by this process
_lock = threading.Lock()


def _run(pid: str, body: dict) -> None:
    from agent.agent import run_agent  # lazy: keeps the server importable without claude installed
    try:
        run_agent(body.get("room") or {}, style_text=body.get("style_text"), budget_usd=body.get("budget_usd"),
                  scan_path=body.get("scan_path"), scan_wall=body.get("scan_wall"), plan_id=pid)
        st = {"status": "done", "error": None}
    except Exception as e:  # the plan file keeps every audit record written before the failure
        st = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    with _lock:
        _status[pid] = st


def start_plan(body: dict) -> dict:
    pid = uuid.uuid4().hex[:12]
    with _lock:
        _status[pid] = {"status": "running", "error": None}
    threading.Thread(target=_run, args=(pid, body), daemon=True, name=f"plan-{pid}").start()
    return {"plan_id": pid, "plan_url": store.plan_url(pid)}


def read_plan(pid: str) -> dict | None:
    with _lock:
        st = _status.get(pid)
    try:
        plan = store.get(pid)
    except (KeyError, ValueError, FileNotFoundError):
        if st and st["status"] == "running":  # thread hasn't created the plan file yet
            return {"plan_id": pid, "plan_url": store.plan_url(pid), "items": [], "audit": [], **st}
        if st:
            return {"plan_id": pid, "items": [], "audit": [], **st}
        return None
    plan = {k: v for k, v in plan.items() if k != "state"}  # tool-private state (vectors) stays server-side
    plan.update(st or {"status": "done", "error": None})
    return plan


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # CORS preflight
        self._send(204, {})

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/api/health":
            return self._send(200, {"ok": True})
        if path.startswith("/api/plan/"):
            plan = read_plan(path.rsplit("/", 1)[-1])
            return self._send(200, plan) if plan else self._send(404, {"error": "no such plan"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?", 1)[0].rstrip("/") != "/api/plan":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except ValueError as e:
            return self._send(400, {"error": f"bad JSON: {e}"})
        room = body.get("room") or {}
        if not body.get("scan_path") and not all(isinstance(room.get(k), (int, float))
                                                 for k in ("wall", "depth", "door_width", "door_height")):
            return self._send(400, {"error": "room needs wall, depth, door_width, door_height in inches (or scan_path)"})
        self._send(202, start_plan(body))

    def log_message(self, fmt, *args):  # quieter: one line per request
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Room Furnisher HTTP API for the web app")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    print(f"Room Furnisher API on http://{a.host}:{a.port} (CORS {ORIGIN})", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
