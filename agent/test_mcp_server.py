"""A6 MCP server tests. Offline by default (agent.tools mocked, plans in a temp dir).

LIVE=1 also starts the real stdio server as a subprocess and lists its tools with the mcp client.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agent import mcp_server, store, tools

REPO = Path(__file__).resolve().parent.parent
EXPECTED = {"create_plan", *(s["name"] for s in tools.TOOL_SPECS)}


class _TempPlans(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": self._tmp.name,
                                                 "PUBLIC_BASE_URL": "https://rooms.example"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class InProcess(_TempPlans):
    def run_client(self, fn, mode="auto"):
        async def go():
            async with Client(mcp_server.build_server(), mode=mode) as c:
                return await fn(c)
        return anyio.run(go)

    def test_list_tools_has_all_nine_with_schemas(self):
        for mode in ("auto", "legacy"):
            res = self.run_client(lambda c: c.list_tools(), mode=mode)
            by = {t.name: t for t in res.tools}
            self.assertEqual(set(by), EXPECTED, mode)
            self.assertEqual(len(by), 9)
            for spec in tools.TOOL_SPECS:
                self.assertEqual(by[spec["name"]].input_schema, spec["input_schema"])
                self.assertTrue(by[spec["name"]].description)
            self.assertEqual(by["create_plan"].input_schema["type"], "object")

    def test_create_plan_returns_plan_url_and_stores_plan(self):
        res = self.run_client(lambda c: c.call_tool("create_plan", {}))
        self.assertFalse(res.is_error)
        sc = res.structured_content
        self.assertEqual(sc["plan_url"], f"https://rooms.example/plan/{sc['plan_id']}")
        self.assertIn(f"Open your room: {sc['plan_url']}", res.content[0].text)
        plan = store.get(sc["plan_id"])
        self.assertEqual(plan["audit"][0]["step"], "agent")
        self.assertEqual(plan["audit"][0]["source"]["kind"], "template")

    def test_pick_through_server_calls_agent_tools(self):
        fake = {"plan_id": "p1", "plan_url": store.plan_url("p1"), "slot": "sofa",
                "picked": {"product_id": "x"}, "rejected": []}
        with mock.patch.object(tools, "pick", return_value=fake) as m:
            res = self.run_client(lambda c: c.call_tool("pick", {"plan_id": "p1", "slot": "sofa",
                                                                  "budget_usd": 500}))
        m.assert_called_once_with(plan_id="p1", slot="sofa", budget_usd=500)
        self.assertFalse(res.is_error)
        self.assertEqual(res.structured_content["plan_url"], "https://rooms.example/plan/p1")
        self.assertTrue(res.content[0].text.startswith("Open your room: https://rooms.example/plan/p1"))

    def test_rule_refusal_is_a_normal_result_with_link(self):
        refusal = {"ok": False, "error": "no verified Senso check", "plan_id": "p1"}
        with mock.patch.object(tools, "cart_add", return_value=refusal):
            res = self.run_client(lambda c: c.call_tool("cart_add", {"plan_id": "p1", "slot": "rug",
                                                                      "why": "w"}))
        self.assertFalse(res.is_error)
        self.assertFalse(res.structured_content["ok"])
        self.assertEqual(res.structured_content["plan_url"], "https://rooms.example/plan/p1")

    def test_errors_come_back_as_tool_errors(self):
        with mock.patch.object(tools, "senso_check", side_effect=ValueError("unknown slot 'bed'")):
            res = self.run_client(lambda c: c.call_tool("senso_check", {"plan_id": "p1", "slot": "bed"}))
        self.assertTrue(res.is_error)
        self.assertIn("unknown slot", res.structured_content["error"])
        self.assertIn("plan_url", res.structured_content)


@unittest.skipUnless(os.environ.get("LIVE") == "1", "LIVE=1 starts the real stdio server")
class LiveStdio(_TempPlans):
    def test_stdio_list_tools_and_create_plan(self):
        params = StdioServerParameters(command=sys.executable, args=["-m", "agent.mcp_server"], cwd=str(REPO),
                                       env={"ROOM_FURNISHER_PLANS_DIR": self._tmp.name})

        async def go():
            async with Client(params) as c:
                listed = await c.list_tools()
                made = await c.call_tool("create_plan", {})
                return listed, made
        listed, made = anyio.run(go)
        self.assertEqual({t.name for t in listed.tools}, EXPECTED)
        self.assertIn("/plan/", made.structured_content["plan_url"])


if __name__ == "__main__":
    unittest.main()
