"""A5 tests: run_agent on Claude Code headless. Offline: subprocess is mocked with a stream-json sample.

The init / assistant-text / result events follow a real `claude -p --output-format stream-json --verbose` capture
(Claude Code 2.1.329); the tool_use / tool_result events are hand-written in the same shape, since the MCP server
(A6) did not exist when this was written. LIVE=1 runs one real agent once agent/mcp_server.py exists.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from agent import agent, store, tools

P = "mcp__room_furnisher__"
FAKE = "placeholder-value-must-not-leak"


def _tool_use(i, name, **inp):
    return {"type": "assistant", "message": {"model": "claude-opus-5-5", "role": "assistant",
            "content": [{"type": "tool_use", "id": f"toolu_{i}", "name": P + name, "input": inp}]}}


def _tool_result(i, content, is_error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"toolu_{i}", "content": content, "is_error": is_error}]}}


def sample(pid):
    return [
        {"type": "system", "subtype": "init", "tools": [P + "pick"], "model": "claude-opus-5-5",
         "mcp_servers": [{"name": "room_furnisher", "status": "connected", "source": "dynamic"}],
         "permissionMode": "dontAsk"},
        {"type": "assistant", "message": {"model": "claude-opus-5-5", "role": "assistant",
                                          "content": [{"type": "text", "text": "Starting with the sofa."}]}},
        _tool_use(1, "style_match", plan_id=pid, slot="sofa"),
        _tool_result(1, '{"ok": true}'),
        _tool_use(2, "pick", plan_id=pid, slot="sofa"),
        _tool_result(2, '{"picked": {"product_id": "x"}}'),
        _tool_use(3, "cart_add", plan_id=pid, slot="sofa", why="Fits the 88 in wall."),
        _tool_result(3, "boom", is_error=True),
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
        _tool_use(4, "get_plan", plan_id=pid),
        _tool_result(4, "{}"),
        {"type": "assistant", "message": {"model": "claude-opus-5-5", "role": "assistant",
                                          "content": [{"type": "text", "text": "Cart: 1 sofa."}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Cart: 1 sofa.", "num_turns": 9,
         "duration_ms": 1234},
    ]


class FakeProc:
    def __init__(self, lines, returncode=0, block=False):
        self.returncode = None
        self._rc = returncode
        self.killed = False
        self._stop = threading.Event()
        if block:
            def gen():
                yield lines[0]
                self._stop.wait(5)
            self.stdout = gen()
        else:
            self.stdout = io.StringIO("".join(lines))

    def wait(self, timeout=None):
        self.returncode = -9 if self.killed else self._rc
        return self.returncode

    def kill(self):
        self.killed = True
        self._stop.set()


class RunAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": self.tmp.name,
                                         "ANTHROPIC_API_KEY": FAKE, "ANTHROPIC_AUTH_TOKEN": FAKE}),
            mock.patch.object(agent, "check_claude"),
            mock.patch.object(tools, "analyze_room", return_value={}),
            mock.patch.object(tools, "get_plan", side_effect=lambda pid: store.get(pid)),
        ]
        self.mocks = [p.start() for p in patches]
        self.analyze = self.mocks[2]
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.tmp.cleanup)
        self.popen_calls = []

    def _popen(self, rc=0, block=False, events=None):
        def fake(cmd, **kw):
            pid = cmd[cmd.index("-p") + 1].split("furnish plan `")[1].split("`")[0]
            evs = events(pid) if events else sample(pid)
            self.popen_calls.append((cmd, kw))
            return FakeProc([json.dumps(e) + "\n" for e in evs], rc, block)
        return mock.patch.object(agent.subprocess, "Popen", side_effect=fake)

    def test_command_line_and_env(self):
        with self._popen():
            agent.run_agent({"wall": 88, "depth": 120, "door_width": 30, "door_height": 80}, style_text="oak",
                            budget_usd=500)
        cmd, kw = self.popen_calls[0]
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "mcp__room_furnisher__*")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")
        cfg = json.loads(cmd[cmd.index("--mcp-config") + 1])
        srv = cfg["mcpServers"]["room_furnisher"]
        self.assertEqual(srv["args"], ["-m", "agent.mcp_server"])
        self.assertEqual(srv["env"]["PYTHONPATH"], str(agent.REPO))
        self.assertEqual(srv["env"]["ROOM_FURNISHER_PLANS_DIR"], self.tmp.name)
        self.assertNotIn("ANTHROPIC_API_KEY", kw["env"])
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", kw["env"])
        self.assertNotIn(FAKE, json.dumps(cmd))
        self.assertEqual(kw["cwd"], str(agent.REPO))
        prompt = cmd[2]
        self.assertIn("budget_usd=500", prompt)
        self.assertNotIn("{{", prompt)
        self.analyze.assert_called_once()
        self.assertEqual(self.analyze.call_args.kwargs["exact"],
                         {"wall": 88.0, "depth": 120.0, "door_width": 30.0, "door_height": 80.0})
        self.assertEqual(self.analyze.call_args.kwargs["style_text"], "oak")

    def test_audit_per_tool_call_and_text(self):
        seen = []
        with self._popen():
            plan = agent.run_agent({}, style_text="oak", on_event=seen.append)
        recs = [r for r in plan["audit"] if r["step"] == "agent"]
        self.assertEqual(recs, seen)
        calls = [r for r in recs if r.get("status") == "called"]
        self.assertEqual([r["decision"] for r in calls],
                         ["call style_match", "call pick", "call cart_add", "call get_plan"])
        for r in calls:
            self.assertEqual(r["source"]["kind"], "claude")
            self.assertEqual(r["source"]["via"], "claude_code")
            self.assertTrue(r["ts"])
        self.assertEqual(calls[0]["item_slot"], "sofa")
        self.assertEqual(calls[2]["input"]["why"], "Fits the 88 in wall.")
        said = [r["why"] for r in recs if r["decision"] == "said"]
        self.assertEqual(said, ["Starting with the sofa.", "Cart: 1 sofa."])
        errs = [r for r in recs if r.get("status") == "error"]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["decision"], "cart_add failed")
        self.assertEqual(errs[0]["source"]["kind"], "template")
        self.assertEqual(recs[-1]["status"], "done")
        self.assertIsNone(self.analyze.call_args.kwargs["exact"])

    def test_estimated_measurements_are_not_passed_as_exact(self):
        with self._popen():
            agent.run_agent({"wall": {"value_in": 88, "error_in": 4, "source": "estimated:door"},
                             "depth": {"value_in": 120, "error_in": 0, "source": "user"}})
        self.assertEqual(self.analyze.call_args.kwargs["exact"], {"depth": 120.0})

    def test_timeout_kills_and_audits(self):
        with self._popen(block=True), mock.patch.object(agent, "TIMEOUT_S", 0.3):
            with self.assertRaises(agent.AgentTimeout) as ctx:
                agent.run_agent({})
        plan = store.get(ctx.exception.plan_id)
        self.assertEqual(plan["audit"][-1]["status"], "timeout")

    def test_nonzero_exit_raises(self):
        def evs(pid):
            return [{"type": "result", "subtype": "error", "is_error": True, "result": "Not logged in"}]
        with self._popen(rc=1, events=evs):
            with self.assertRaises(agent.AgentError) as ctx:
                agent.run_agent({})
        self.assertIn("sign in", str(ctx.exception))
        self.assertEqual(store.get(ctx.exception.plan_id)["audit"][-1]["status"], "error")

    def test_mcp_server_failed(self):
        def evs(pid):
            return [{"type": "system", "subtype": "init",
                     "mcp_servers": [{"name": "room_furnisher", "status": "failed"}]}]
        with self._popen(events=evs):
            with self.assertRaisesRegex(agent.AgentError, "did not start"):
                agent.run_agent({})


class CheckClaude(unittest.TestCase):
    def test_missing(self):
        with mock.patch.object(agent.shutil, "which", return_value=None):
            with self.assertRaisesRegex(agent.AgentError, "sign in"):
                agent.check_claude()

    def test_not_signed_in(self):
        out = mock.Mock(stdout='{"loggedIn": false}')
        with mock.patch.object(agent.shutil, "which", return_value="/x/claude"), \
                mock.patch.object(agent.subprocess, "run", return_value=out) as run, \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": FAKE}):
            with self.assertRaisesRegex(agent.AgentError, "not signed in"):
                agent.check_claude()
        self.assertNotIn("ANTHROPIC_API_KEY", run.call_args.kwargs["env"])

    def test_signed_in(self):
        out = mock.Mock(stdout='{"loggedIn": true, "authMethod": "claude.ai"}')
        with mock.patch.object(agent.shutil, "which", return_value="/x/claude"), \
                mock.patch.object(agent.subprocess, "run", return_value=out):
            agent.check_claude()


class StaticFiles(unittest.TestCase):
    def test_mcp_json(self):
        cfg = json.loads(agent.MCP_JSON.read_text())
        srv = cfg["mcpServers"]["room_furnisher"]
        self.assertEqual(srv["args"], ["-m", "agent.mcp_server"])
        self.assertTrue(srv["command"].endswith("/.venv/bin/python"))

    def test_prompt_no_budget(self):
        p = agent.build_prompt("abc123", None)
        self.assertIn("abc123", p)
        self.assertNotIn("{{", p)
        for t in ("style_match", "fit_options", "pick", "senso_check", "cart_add", "swap", "get_plan"):
            self.assertIn(t, p)


@unittest.skipUnless(os.environ.get("LIVE") == "1" and (agent.REPO / "agent" / "mcp_server.py").exists(),
                     "LIVE=1 and agent/mcp_server.py (A6) needed")
class Live(unittest.TestCase):
    def test_real_run(self):
        events = []
        plan = agent.run_agent({"wall": 120, "depth": 150, "door_width": 32, "door_height": 80},
                               style_text="warm minimal, light oak", on_event=events.append)
        print(json.dumps({"plan_id": plan["plan_id"], "cart": plan["cart"], "events": len(events)}, indent=1))
        self.assertTrue(any(e.get("status") == "called" for e in events))
        self.assertTrue(plan["cart"]["no_purchase"])


if __name__ == "__main__":
    unittest.main()
