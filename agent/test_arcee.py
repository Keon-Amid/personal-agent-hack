"""Run: python3 -m unittest agent.test_arcee  (no network, no key)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

from agent import arcee, store, tools

FACTS = {"product": "GULLVALLA Sofa", "price_usd": 449.0, "size_in": {"w": 71.625, "d": 32.625, "h": 30.75},
         "fit_verdict": "fits", "fit_math": ["width 71.625 in <= 88 in (user)"], "style_rank": 1,
         "senso": {"verified": 8, "claims": 9}, "rejected": []}


class Score(unittest.TestCase):
    def test_grounded_with_price_and_fit(self):
        q = arcee.score("The GULLVALLA fits: 71.625 in on your 88 in wall, $449.", FACTS)
        self.assertEqual((q["quality"], q["grounded"], q["names_price"], q["names_fit"]), (1.0, True, True, True))

    def test_invented_number_is_not_grounded(self):
        q = arcee.score("It fits with 20 inches to spare for $449.", FACTS)
        self.assertFalse(q["grounded"])
        self.assertEqual(q["invented_numbers"], [20.0])

    def test_empty_scores_zero(self):
        self.assertEqual(arcee.score("", FACTS)["quality"], 0.0)


class ArceeWhy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": self.tmp.name})
        self.env.start()
        self.pid = store.new_plan()["plan_id"]
        item = {"slot": "sofa", "product_id": "p1", "name": "GULLVALLA Sofa", "price_usd": 449.0,
                "dims_in": FACTS["size_in"], "fit": {"verdict": "fits", "results": [{"math": FACTS["fit_math"][0]}]},
                "why": "Claude's why", "why_source": {"kind": "claude"}, "rejected": []}
        tools._commit(self.pid, [], lambda p: p["items"].append(item))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_keeps_claude_why_and_audits_cost(self):
        fake = {"text": "GULLVALLA fits your 88 in wall at $449.", "model": "m", "latency_ms": 900,
                "input_tokens": 200, "output_tokens": 80, "reasoning_tokens": 50, "reasoning": "...",
                "cost_usd": 0.0002}
        with mock.patch.object(arcee, "write_why", return_value=fake):
            out = arcee.arcee_why(self.pid, "sofa", "m")
        self.assertTrue(out["ok"])
        plan = tools.get_plan(self.pid)
        it = plan["items"][0]
        self.assertEqual((it["why"], it["why_source"]), ("Claude's why", {"kind": "claude"}))
        self.assertEqual(it["why_alternatives"][0]["source"]["kind"], "arcee")
        rec = plan["audit"][-1]
        self.assertEqual((rec["source"]["kind"], rec["source"]["cost_usd"], rec["source"]["latency_ms"]),
                         ("arcee", 0.0002, 900))

    def test_failure_is_audited_not_raised(self):
        with mock.patch.object(arcee, "write_why", side_effect=RuntimeError("ARCEE_API_KEY is not set")):
            out = arcee.arcee_why(self.pid, "sofa", "m")
        self.assertFalse(out["ok"])
        self.assertEqual(tools.get_plan(self.pid)["audit"][-1]["decision"], "arcee why failed")


if __name__ == "__main__":
    unittest.main()
