"""Run: python3 -m unittest agent.test_senso_kb  (no network, no key)."""
import json
import unittest
from unittest import mock

from agent import senso_kb as kb

P = json.loads(kb.PRODUCTS.read_text())["products"]
KIVIK = next(p for p in P if p["id"] == "ikea-kivik-sofa-tibbleby-beige-gray-39440593")


class Doc(unittest.TestCase):
    def test_kivik_doc_has_real_numbers(self):
        title, text = kb.product_doc(KIVIK)
        self.assertEqual(title, "IKEA 394.405.93 KIVIK Sofa - Tibbleby beige/gray")
        self.assertIn("width 89.75 in", text)
        self.assertIn("box 1: 37.5 in wide x 72.5 in long x 19.75 in high", text)
        self.assertIn("$799", text)
        self.assertIn(KIVIK["source_url"], text)

    def test_every_product_builds(self):
        for p in P:
            t, x = kb.product_doc(p)
            self.assertTrue(t and x)

    def test_no_price(self):
        p = next(p for p in P if p["price_usd"] is None)
        self.assertIn("showed no price", kb.product_doc(p)[1])


class Load(unittest.TestCase):
    def test_created_then_unchanged_then_409(self):
        idx = {}
        with mock.patch.object(kb, "_req", return_value=(202, {"id": "c1", "kb_node_id": "n1",
                                                               "processing_status": "processing"})) as r:
            self.assertEqual(kb.load(P[:2], idx)["created"], 2)
            self.assertEqual(r.call_count, 2)
        with mock.patch.object(kb, "_req") as r:
            self.assertEqual(kb.load(P[:2], idx)["unchanged"], 2)
            r.assert_not_called()
        with mock.patch.object(kb, "_req", return_value=(409, {"message": "duplicate"})):
            c = kb.load(P[2:3], {})
        self.assertEqual(c["already_in_senso"], 1)

    def test_stops_on_auth_error(self):
        with mock.patch.object(kb, "_req", return_value=(401, {"message": "bad key"})) as r:
            c = kb.load(P[:5], {})
        self.assertEqual((c["failed"], r.call_count), (1, 1))

    def test_rules_doc(self):
        idx = {}
        with mock.patch.object(kb, "_req", return_value=(202, {"kb_node_id": "n"})) as r:
            kb.load([], idx, rules=True)
        self.assertIn("36 inches", r.call_args[0][2]["text"])
        self.assertIn("_rules", idx)


if __name__ == "__main__":
    unittest.main()
