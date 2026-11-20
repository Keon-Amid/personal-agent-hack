import json
import unittest
from pathlib import Path

from fit import measurement
from fit.claims import claim_text, claims_for
from fit.options import check_all, room

P = {p["id"]: p for p in json.loads((Path(__file__).parent.parent / "data/products.json").read_text())["products"]}
RM = room(measurement(88), measurement(150), measurement(30), measurement(80))
KIVIK = P["ikea-kivik-sofa-tibbleby-beige-gray-39440593"]


class Claims(unittest.TestCase):
    def test_sofa_claims_name_article_and_rule(self):
        cs = claims_for(KIVIK, check_all(KIVIK, RM))
        self.assertEqual([c["rule"] for c in cs], ["wall", "walkway", "doorway", "price"])
        for c in cs:
            self.assertIn("394.405.93", c["text"])
        self.assertTrue(cs[0]["text"].startswith("Under our wall-fit rule"))
        self.assertIn("Our catalog lists the KIVIK", cs[0]["text"])
        self.assertIn("89.75 inches wide", cs[0]["text"])
        self.assertIn("box 1 as 37.5 inches wide, 72.5 inches long and 19.75 inches high", cs[2]["text"])

    def test_rug_uses_rug_rule(self):
        rug = next(p for p in P.values() if p["category"] == "rug")
        rules = [c["rule"] for c in claims_for(rug, check_all(rug, RM))]
        self.assertIn("rug", rules)
        self.assertNotIn("wall", rules)

    def test_no_price_no_price_claim(self):
        p = next(p for p in P.values() if p["price_usd"] is None)
        self.assertNotIn("price", [c["rule"] for c in claims_for(p, check_all(p, RM))])

    def test_text_joins(self):
        self.assertTrue(claim_text(KIVIK, check_all(KIVIK, RM)).startswith("Under our wall-fit rule"))


if __name__ == "__main__":
    unittest.main()
