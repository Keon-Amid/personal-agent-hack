"""Offline check of scripts/eval_guardrails.py: Superlinked and Senso are faked, so this proves only the eval's
wiring and pass/fail logic. The real numbers come from running the script (contracts/eval.json).
Lives in agent/ so the standard full test command (pytest server/ agent/ data/ fit/) runs it.
Run: .venv/bin/python -m pytest -q agent/test_eval_guardrails.py
"""
from __future__ import annotations

import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import eval_guardrails as ev  # noqa: E402
from agent.test_tools import fake_analyze_room, fake_style_match  # noqa: E402

_PRODUCTS = json.loads((REPO / "data" / "products.json").read_text())["products"]
WIDTHS = {f'{p["dims_in"]["w"]:g}' for p in _PRODUCTS} | \
    {f'{b["w"]:g}' for p in _PRODUCTS for b in p.get("packages_in") or []}


def fake_senso():
    """'conflict' when the text states a width no catalog product has, else 'verified'."""
    m = types.ModuleType("agent.senso")

    def check(text, question):
        stated = re.findall(r"as ([\d.]+) inches wide", text)
        wrong = [w for w in stated if w not in WIDTHS]
        v = "conflict" if wrong else "verified"
        return {"check_id": "fake", "accuracy_pct": 0.0 if wrong else 100.0, "cached": False,
                "claims": [{"claim": f"The sofa is {(wrong or stated or ['?'])[0]} inches wide.", "verdict": v,
                            "quote": "fake"}]}
    m.check = check
    m.verdict_ok = lambda s: any(c["verdict"] == "verified" for c in s["claims"]) and \
        not any(c["verdict"] == "conflict" for c in s["claims"])
    return m


class EvalGuardrailsTest(unittest.TestCase):
    def test_all_scenarios_pass_with_fakes(self):
        with mock.patch("data.sie.analyze_room", side_effect=fake_analyze_room), \
                mock.patch("data.sie.style_match", side_effect=fake_style_match), \
                mock.patch.dict(sys.modules, {"agent.senso": fake_senso()}):
            res = ev.run(out=None)
        failed = [(s["name"], s["happened"]) for s in res["scenarios"] if not s["pass"]]
        self.assertEqual(failed, [])
        self.assertEqual(res["summary"]["total"], 6)
        self.assertGreater(res["summary"]["no_fit_or_refused_events"], 0)
        self.assertTrue(all(sc["counts"] for sc in res["scenarios"]))
        self.assertIn("passed 6/6", ev.table(res))

    def test_senso_conflict_on_another_claim_does_not_pass(self):
        """A conflict on some other claim must not count as 'Senso caught the wrong width'."""
        m = fake_senso()
        truthful = m.check

        def check(text, q):  # width claim always "verified"; an unrelated rule claim conflicts only on the bad text
            res = truthful(text, q)
            wrong = res["claims"][0]["verdict"] == "conflict"
            return {**res, "claims": [{"claim": "The sofa is wide.", "verdict": "verified", "quote": "q"}]
                    + ([{"claim": "Rule: no halogen lamps", "verdict": "conflict", "quote": "q"}] if wrong else [])}
        m.check = check
        with mock.patch("data.sie.analyze_room", side_effect=fake_analyze_room), \
                mock.patch("data.sie.style_match", side_effect=fake_style_match), \
                mock.patch.dict(sys.modules, {"agent.senso": m}):
            ctx: dict = {}
            import tempfile, os
            with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": d}):
                ev.too_wide_wall(ctx)
                r = ev.senso_catches_wrong_fact(ctx)
        self.assertFalse(r["passed"])
        self.assertEqual(r["blocked"], 0)

    def test_over_budget_skips_unpriced_sofa_without_crashing(self):
        """A swap landing on a null-price sofa (SLATORP) must be skipped, not raise TypeError."""
        from agent import tools
        real_pick = tools.pick
        slatorp = "ikea-slatorp-sofa-hakebo-dark-gray-30594387"
        state = {"n": 0}

        def pick(pid, slot, *a, **k):  # part B's (no-budget) pick lands on a null-price sofa
            out = real_pick(pid, slot, *a, **k)
            state["n"] += 1
            if state["n"] == 2 and out.get("picked"):
                out = dict(out, picked=dict(out["picked"], product_id=slatorp, price_usd=None))
            return out
        with mock.patch("data.sie.analyze_room", side_effect=fake_analyze_room), \
                mock.patch("data.sie.style_match", side_effect=fake_style_match), \
                mock.patch.dict(sys.modules, {"agent.senso": fake_senso()}), \
                mock.patch.object(tools, "pick", side_effect=pick):
            import tempfile, os
            with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": d}):
                r = ev.over_budget({})
        self.assertGreaterEqual(state["n"], 2, "the null-price path was not exercised")
        self.assertNotIn("error", r["happened"])
        self.assertTrue(r["passed"], r["happened"])
        self.assertIn("price_usd", ev._short({"product_id": slatorp, "name": "S", "price_usd": None,
                                              "dims_in": {"w": 1}, "fit": {"verdict": "fits", "results": []}}))
        self.assertEqual(ev._usd(None), "no price")


if __name__ == "__main__":
    unittest.main()
