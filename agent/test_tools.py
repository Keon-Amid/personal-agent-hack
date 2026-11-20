"""T: agent.tools wired to fit/ and the plan store. Offline: data.sie, agent.senso and agent.room are mocked."""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from agent import store, tools

KIVIK = "ikea-kivik-sofa-tibbleby-beige-gray-39440593"     # 89.75 in wide
UPPLAND = "ikea-uppland-sofa-blekinge-white-19384116"      # 88.25 in
LILLESATER = "ikea-lillesater-sofa-axvall-off-white-40619085"  # 79.125 in
GLOSTAD = "ikea-glostad-sofa-knisa-dark-gray-40595942"     # 70.125 in
GULLVALLA = "ikea-gullvalla-sofa-silkeryd-dark-gray-beige-70618503"  # 71.625 in
HYLTARP = "ikea-hyltarp-sofa-gransel-gray-89514930"        # 91.375 in
KIVIK_BLACK = "ikea-kivik-sofa-grann-bomstad-black-80519531"  # 89.375 in
STYLE_ORDER = [KIVIK, UPPLAND, LILLESATER, GLOSTAD, GULLVALLA, HYLTARP, KIVIK_BLACK]
EXACT = {"wall": 88, "depth": 150, "door_width": 30, "door_height": 80}


def fake_analyze_room(room_photo=None, style_text=None):
    det = [{"style": "scandinavian", "score": 0.1}] if room_photo is not None and not style_text else None
    return {"vec": [0.0, 1.0], "style_text": style_text or "scandinavian style living room", "detected_style": det}


def fake_style_match(products, category, emb, room=None, **kw):
    order = STYLE_ORDER if category == "sofa" else [p["id"] for p in products if p["category"] == category]
    names = {p["id"]: p["name"] for p in products}
    ranked = [{"id": pid, "name": names[pid], "product_styles": [{"style": "scandinavian", "score": 0.08}],
               "style_fused": round(0.03 - i * 0.001, 6), "photo_rank": i + 1, "photo_score": 0.1 - i * 0.01,
               "text_rank": i + 1, "text_score": 0.9 - i * 0.1, "style_rank": i + 1}
              for i, pid in enumerate(order)]
    return {"category": category, "style_text": room["style_text"], "detected_style": room["detected_style"],
            "source": {"kind": "superlinked", "embed_model": "mock", "rerank_model": "mock", "fusion": "mock"},
            "ranked": ranked}


def fake_senso(verdict: str = "verified"):
    m = types.ModuleType("agent.senso")
    m.build_claim = mock.Mock(side_effect=lambda item: f'The {item["name"]} costs ${item["price_usd"]:g}.')
    m.check = mock.Mock(return_value={"check_id": "mock-eval", "accuracy_pct": 100.0, "claims": [
        {"claim": "price", "verdict": verdict, "quote": "mock quote"},
        {"claim": "The room wall is 88 inches wide.", "verdict": "unsupported", "quote": None}]})
    m.verdict_ok = lambda s: any(c["verdict"] == "verified" for c in s["claims"]) and \
        not any(c["verdict"] == "conflict" for c in s["claims"])
    return m


def fake_room(wall=88, err=4):
    m = types.ModuleType("agent.room")
    m.estimate = mock.Mock(return_value=({
        "wall": {"value_in": float(wall), "error_in": float(err), "source": "estimated:door"},
        "depth": {"value_in": 150.0, "error_in": 6.0, "source": "estimated:door"},
        "door_width": {"value_in": 30.0, "error_in": 1.0, "source": "estimated:door"},
        "door_height": {"value_in": 80.0, "error_in": 2.0, "source": "estimated:door"}},
        [{"ts": "2026-11-20T20:00:00Z", "step": "estimate_room", "source": {"kind": "superlinked", "model": "mock"},
          "decision": "estimated wall, door_width, door_height", "status": "estimated", "why": "mock"}]))
    return m


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"ROOM_FURNISHER_PLANS_DIR": self.tmp.name})
        self.env.start()
        self.sie_a = mock.patch("data.sie.analyze_room", side_effect=fake_analyze_room)
        self.sie_s = mock.patch("data.sie.style_match", side_effect=fake_style_match)
        self.analyze = self.sie_a.start()
        self.match = self.sie_s.start()
        self.senso = fake_senso()
        self.mods = mock.patch.dict(sys.modules, {"agent.senso": self.senso, "agent.room": fake_room()})
        self.mods.start()
        self.pid = store.new_plan()["plan_id"]

    def tearDown(self):
        for p in (self.mods, self.sie_s, self.sie_a, self.env):
            p.stop()
        self.tmp.cleanup()

    def exact_room(self):
        out = tools.analyze_room(self.pid, style_text="warm minimal, light oak", exact=EXACT)
        self.assertTrue(out["ok"], out)
        return out

    def assert_all_ts(self):
        plan = tools.get_plan(self.pid)
        self.assertTrue(plan["audit"])
        for rec in plan["audit"]:
            self.assertRegex(rec.get("ts") or "", r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", rec)
            self.assertIn("source", rec)
            self.assertIn("kind", rec["source"])
        return plan

    def test_returns_plan_id_and_url(self):
        out = self.exact_room()
        self.assertEqual(out["plan_id"], self.pid)
        self.assertTrue(out["plan_url"].endswith(f"/plan/{self.pid}"))
        self.assertEqual(out["room"]["wall"], {"value_in": 88.0, "error_in": 0.0, "source": "user"})
        self.assertEqual(out["style"]["style_text"], "warm minimal, light oak")
        for fn in (tools.style_match, tools.fit_options, tools.pick):
            res = fn(self.pid, "sofa")
            self.assertEqual((res["plan_id"], res["plan_url"]), (out["plan_id"], out["plan_url"]))
        self.assertNotIn("state", tools.get_plan(self.pid))

    def test_kivik_too_wide_ends_in_rejected_exact(self):
        self.exact_room()
        out = tools.pick(self.pid, "sofa")
        self.assertEqual(out["picked"]["product_id"], LILLESATER)
        self.assertEqual(out["picked"]["fit"]["verdict"], "fits")
        self.assertEqual(out["picked"]["why_source"], {"kind": "template"})
        kivik = next(r for r in out["rejected"] if r["product_id"] == KIVIK)
        self.assertEqual(kivik["status"], "no_fit")
        self.assertIn("89.75", kivik["why"])
        plan = self.assert_all_ts()
        self.assertTrue(any(r["step"] == "pick" and r.get("product_id") == KIVIK and r["decision"] == "rejected"
                            for r in plan["audit"]))
        self.assertEqual(plan["items"][0]["rejected"][0]["product_id"], KIVIK)

    def test_estimated_wall_makes_wide_sofas_unsure(self):
        photo = base64.b64encode(b"\xff\xd8fakejpeg").decode()
        out = tools.analyze_room(self.pid, photo_b64=photo)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["room"]["wall"]["source"], "estimated:door")
        self.assertEqual(out["style"]["detected_style"], "scandinavian")
        res = tools.pick(self.pid, "sofa")
        kivik = next(r for r in res["rejected"] if r["product_id"] == KIVIK)
        self.assertEqual(kivik["status"], "unsure")
        self.assertNotIn(res["picked"]["product_id"], (KIVIK, UPPLAND))
        # exact numbers override the estimate key by key: now KIVIK is a hard no_fit
        tools.analyze_room(self.pid, exact={"wall": 88})
        res = tools.pick(self.pid, "sofa")
        self.assertEqual(next(r for r in res["rejected"] if r["product_id"] == KIVIK)["status"], "no_fit")
        self.assert_all_ts()

    def test_cart_refuses_without_verified_check_then_accepts(self):
        self.exact_room()
        tools.pick(self.pid, "sofa")
        out = tools.cart_add(self.pid, "sofa", "It fits and matches.")
        self.assertFalse(out["ok"])
        self.assertIn("senso_check", out["error"])
        self.assertEqual(tools.get_plan(self.pid)["cart"]["items"], [])

        self.senso.check.return_value = {"check_id": "c1", "accuracy_pct": 50.0, "claims": [
            {"claim": "price", "verdict": "conflict", "quote": "price $1099"},
            {"claim": "walkway", "verdict": "verified", "quote": "36 inches"}]}
        chk = tools.senso_check(self.pid, "sofa")
        self.assertFalse(chk["ok"])
        out = tools.cart_add(self.pid, "sofa", "It fits and matches.")
        self.assertFalse(out["ok"])

        self.senso.check.return_value = {"check_id": "c2", "accuracy_pct": 100.0, "claims": [
            {"claim": "walkway", "verdict": "verified", "quote": "36 inches"}]}
        chk = tools.senso_check(self.pid, "sofa")
        self.assertTrue(chk["ok"])
        out = tools.cart_add(self.pid, "sofa", "Fits the 88 in wall with the walkway clear.")
        self.assertTrue(out["ok"], out)
        self.assertEqual([c["product_id"] for c in out["cart"]["items"]], [LILLESATER])
        self.assertEqual(out["cart"]["total_usd"], 999.0)
        self.assertTrue(out["cart"]["no_purchase"])
        plan = self.assert_all_ts()
        item = plan["items"][0]
        self.assertEqual(item["why_source"], {"kind": "claude"})
        self.assertEqual(item["senso"]["check_id"], "c2")
        refusals = [r for r in plan["audit"] if r["step"] == "cart" and r["decision"] == "refused"]
        self.assertEqual(len(refusals), 2)
        cart_rec = [r for r in plan["audit"] if r["step"] == "cart" and r["decision"] == "added to cart"]
        self.assertEqual(cart_rec[0]["source"], {"kind": "claude"})

    # ---------------------------------------------------------------- budget (enforced by the tools)
    def verified(self):
        self.senso.check.return_value = {"check_id": "ok", "accuracy_pct": 100.0, "claims": [
            {"claim": "walkway", "verdict": "verified", "quote": "36 inches"}]}

    def test_per_item_budget_caps_pick_even_if_model_asks_for_more(self):
        self.exact_room()
        self.assertTrue(tools.set_budget(self.pid, per_item_usd=500)["ok"])
        out = tools.pick(self.pid, "sofa", budget_usd=5000)  # the model can't loosen the person's budget
        self.assertLessEqual(out["picked"]["price_usd"], 500)
        self.assertEqual(out["budget_cap_usd"], 500)
        self.assertIn("per-item budget $500", out["budget_cap_why"])
        self.assertEqual(tools.get_plan(self.pid)["budget"], {"total_usd": None, "per_item_usd": 500.0})

    def test_total_budget_counts_picks_before_they_are_carted(self):
        self.exact_room()
        tools.set_budget(self.pid, total_usd=600)
        sofa = tools.pick(self.pid, "sofa")["picked"]
        arm = tools.pick(self.pid, "armchair")
        self.assertAlmostEqual(arm["budget_cap_usd"], 600 - sofa["price_usd"])

    def test_total_budget_shrinks_as_cart_fills(self):
        self.exact_room()
        self.verified()
        tools.set_budget(self.pid, total_usd=600)
        sofa = tools.pick(self.pid, "sofa")["picked"]
        tools.senso_check(self.pid, "sofa")
        self.assertTrue(tools.cart_add(self.pid, "sofa", "fits")["ok"])
        left = 600 - sofa["price_usd"]
        arm = tools.pick(self.pid, "armchair")
        self.assertAlmostEqual(arm["budget_cap_usd"], left)
        if arm["ok"]:
            self.assertLessEqual(arm["picked"]["price_usd"], left)

    def test_cart_refuses_item_that_breaks_a_budget_set_later(self):
        self.exact_room()
        self.verified()
        picked = tools.pick(self.pid, "sofa")["picked"]  # no budget yet: LILLESATER $999
        tools.senso_check(self.pid, "sofa")
        tools.set_budget(self.pid, total_usd=500)
        out = tools.cart_add(self.pid, "sofa", "fits")
        self.assertFalse(out["ok"])
        self.assertIn("over the $500 total budget", out["error"])
        tools.set_budget(self.pid, per_item_usd=300)
        out = tools.cart_add(self.pid, "sofa", "fits")
        self.assertFalse(out["ok"])
        self.assertIn(f"costs ${picked['price_usd']:g}, over the per-item budget of $300", out["error"])
        self.assertEqual(tools.get_plan(self.pid)["cart"]["items"], [])
        plan = self.assert_all_ts()
        self.assertTrue(any(r["decision"] == "budget set" for r in plan["audit"]))

    def test_set_budget_rejects_bad_values_and_clears(self):
        self.assertFalse(tools.set_budget(self.pid, total_usd=-5)["ok"])
        self.assertFalse(tools.set_budget(self.pid, per_item_usd=True)["ok"])
        tools.set_budget(self.pid, total_usd=900)
        self.assertEqual(tools.get_plan(self.pid)["budget"]["total_usd"], 900.0)
        tools.set_budget(self.pid)
        self.assertIsNone(tools.get_plan(self.pid)["budget"])

    def test_swap_never_repeats_and_clears_check_and_cart(self):
        self.exact_room()
        first = tools.pick(self.pid, "sofa")["picked"]["product_id"]
        tools.senso_check(self.pid, "sofa")
        self.assertTrue(tools.cart_add(self.pid, "sofa", "ok")["ok"])
        seen = [first]
        calls = self.match.call_count
        while True:
            out = tools.swap(self.pid, "sofa")
            if not out["ok"]:
                break
            pid = out["picked"]["product_id"]
            self.assertNotIn(pid, seen)
            self.assertEqual(out["excluded"], seen)
            self.assertEqual(out["picked"]["fit"]["verdict"], "fits")
            seen.append(pid)
        self.assertEqual(seen, [LILLESATER, GLOSTAD, GULLVALLA])
        self.assertEqual(self.match.call_count, calls)  # swaps reuse the cached ranking
        self.assertIsNone(out["picked"])
        plan = self.assert_all_ts()
        item = plan["items"][0]
        self.assertEqual(item["product_id"], GULLVALLA)  # nothing left: the last pick stays
        self.assertIsNone(item["senso"])
        self.assertEqual(plan["cart"]["items"], [])
        self.assertEqual(plan["cart"]["total_usd"], 0)
        self.assertTrue(any(r["step"] == "swap" and r["status"] == "none_left" for r in plan["audit"]))

    def test_room_analysis_reused_across_slots(self):
        self.exact_room()
        tools.pick(self.pid, "sofa")
        tools.pick(self.pid, "armchair")
        self.assertEqual(self.analyze.call_count, 1)
        for c in self.match.call_args_list:
            self.assertEqual(c.kwargs["room"]["style_text"], "warm minimal, light oak")

    def test_refusals_and_errors(self):
        out = tools.pick(self.pid, "sofa")
        self.assertFalse(out["ok"])
        self.assertIn("analyze_room", out["error"])
        with self.assertRaises(ValueError):
            tools.pick(self.pid, "bed")
        with self.assertRaises(ValueError):
            tools.get_plan("nope")
        self.exact_room()
        self.assertFalse(tools.senso_check(self.pid, "rug")["ok"])
        self.assertFalse(tools.swap(self.pid, "rug")["ok"])
        self.assert_all_ts()

    def test_superlinked_missing_key_is_an_error_not_a_crash(self):
        self.analyze.side_effect = SystemExit("SIE_API_KEY is not set (put it in .env)")
        out = tools.analyze_room(self.pid, style_text="boho", exact=EXACT)
        self.assertFalse(out["ok"])
        self.assertIn("SIE_API_KEY", out["error"])
        self.assertTrue(tools.fit_options(self.pid, "sofa")["ok"])  # fit works without Superlinked

    def test_budget(self):
        self.exact_room()
        out = tools.pick(self.pid, "sofa", budget_usd=300)
        self.assertEqual(out["picked"]["product_id"], GLOSTAD)
        lil = next(r for r in out["rejected"] if r["product_id"] == LILLESATER)
        self.assertIn("over budget", lil["why"])


if __name__ == "__main__":
    unittest.main()
