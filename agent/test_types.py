"""A1 contract tests: fixture shape, catalog ids, TOOL_SPECS, store round trip. Offline."""
from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path

from agent import store, tools
from agent.types import (AuditRecord, Cart, Item, Plan, SensoCheck, SensoClaim, SLOTS, SOURCE_KINDS, STEPS,
                         audit, now_ts)

REPO = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((REPO / "contracts" / "plan.example.json").read_text())
CATALOG = {p["id"]: p for p in json.loads((REPO / "data" / "products.json").read_text())["products"]}


def required(td) -> set[str]:
    return set(td.__required_keys__)


class FixtureShape(unittest.TestCase):
    def test_plan_keys(self):
        self.assertTrue(FIXTURE["fixture"])
        self.assertLessEqual(required(Plan), set(FIXTURE))
        self.assertTrue(FIXTURE["plan_url"].endswith("/plan/" + FIXTURE["plan_id"]))
        self.assertLessEqual(required(Cart), set(FIXTURE["cart"]))
        self.assertTrue(FIXTURE["cart"]["no_purchase"])

    def test_exact_room(self):
        wall = FIXTURE["room"]["wall"]
        self.assertEqual((wall["value_in"], wall["error_in"], wall["source"]), (88.0, 0.0, "user"))

    def test_items(self):
        self.assertTrue(FIXTURE["items"])
        for it in FIXTURE["items"]:
            self.assertLessEqual(required(Item), set(it), it["slot"])
            self.assertIn(it["slot"], SLOTS)
            self.assertEqual(it["fit"]["verdict"], "fits")
            self.assertIn(it["why_source"]["kind"], ("claude", "template"))
            self.assertLessEqual(required(SensoCheck), set(it["senso"]))
            for c in it["senso"]["claims"]:
                self.assertLessEqual(required(SensoClaim), set(c))

    def test_kivik_rejected_no_fit_and_walkway_verified(self):
        sofa = next(i for i in FIXTURE["items"] if i["slot"] == "sofa")
        kivik = next(r for r in sofa["rejected"] if r["product_id"].startswith("ikea-kivik"))
        self.assertEqual(kivik["status"], "no_fit")
        self.assertIn("89.75", kivik["why"])
        walk = [c for c in sofa["senso"]["claims"] if c["verdict"] == "verified" and "36 inches" in (c["quote"] or "")]
        self.assertTrue(walk)

    def test_audit_records(self):
        for rec in FIXTURE["audit"]:
            self.assertLessEqual(required(AuditRecord), set(rec))
            self.assertIn(rec["step"], STEPS)
            self.assertIn(rec["source"]["kind"], SOURCE_KINDS)

    def test_ids_and_numbers_from_catalog(self):
        for it in FIXTURE["items"]:
            p = CATALOG[it["product_id"]]
            self.assertEqual((it["name"], it["price_usd"], it["dims_in"], it["source_url"]),
                             (p["name"], p["price_usd"], p["dims_in"], p["source_url"]))
            for r in it["rejected"]:
                self.assertIn(r["product_id"], CATALOG)
        for c in FIXTURE["cart"]["items"]:
            self.assertEqual(c["price_usd"], CATALOG[c["product_id"]]["price_usd"])
        for rec in FIXTURE["audit"]:
            if "product_id" in rec:
                self.assertIn(rec["product_id"], CATALOG)
        self.assertAlmostEqual(FIXTURE["cart"]["total_usd"], sum(c["price_usd"] for c in FIXTURE["cart"]["items"]))


class ToolSpecs(unittest.TestCase):
    NAMES = ["analyze_room", "style_match", "fit_options", "pick", "senso_check", "swap", "cart_add", "get_plan"]

    def test_names_match_functions(self):
        self.assertEqual([s["name"] for s in tools.TOOL_SPECS], self.NAMES)
        for spec in tools.TOOL_SPECS:
            fn = getattr(tools, spec["name"])
            params = inspect.signature(fn).parameters
            self.assertEqual(set(spec["input_schema"]["properties"]), set(params), spec["name"])
            need = {n for n, p in params.items() if p.default is inspect.Parameter.empty}
            self.assertEqual(set(spec["input_schema"]["required"]), need, spec["name"])
            self.assertTrue(spec["description"])
            self.assertTrue(fn.__doc__)


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("ROOM_FURNISHER_PLANS_DIR")
        os.environ["ROOM_FURNISHER_PLANS_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("ROOM_FURNISHER_PLANS_DIR", None)
        else:
            os.environ["ROOM_FURNISHER_PLANS_DIR"] = self.old
        self.tmp.cleanup()

    def test_round_trip_and_audit(self):
        plan = store.new_plan(style={"style_text": "warm minimal", "detected_style": None})
        self.assertTrue(plan["plan_url"].endswith("/plan/" + plan["plan_id"]))
        rec = store.append_audit(plan["plan_id"], {"step": "agent", "source": {"kind": "claude"},
                                                   "decision": "started", "why": "test"})
        self.assertIn("ts", rec)
        got = store.get(plan["plan_id"])
        self.assertEqual(got["audit"][-1]["decision"], "started")
        got["state"]["room_vec"] = [0.1, 0.2]
        got["audit"].append({"step": "agent", "source": {"kind": "template"}, "decision": "x", "why": ""})
        store.save(got)
        again = store.get(plan["plan_id"])
        self.assertEqual(again["state"]["room_vec"], [0.1, 0.2])
        self.assertTrue(all("ts" in r for r in again["audit"]))
        self.assertEqual(list(Path(self.tmp.name).glob("*.tmp")), [])

    def test_missing_and_bad_ids(self):
        with self.assertRaises(KeyError):
            store.get("nope")
        with self.assertRaises(ValueError):
            store.get("../etc")

    def test_audit_helper(self):
        rec = audit("pick", product_id="x", decision="picked")
        self.assertEqual(rec["source"], {"kind": "template"})
        self.assertTrue(rec["ts"].endswith("Z") and len(rec["ts"]) == len(now_ts()))
        with self.assertRaises(ValueError):
            audit("bogus")


if __name__ == "__main__":
    unittest.main()
