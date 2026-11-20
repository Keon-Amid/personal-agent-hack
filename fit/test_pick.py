import unittest

from fit.pick import pick

SRC = {"kind": "superlinked", "embed_model": "e", "rerank_model": "r", "fusion": "rrf"}


def opt(i, fit="fits", price=100.0, best=False):
    return {"id": i, "name": i, "fit": fit, "price_usd": price, "rating": 4.2, "review_count": 50,
            "best_value": best, "why": f"no_fit: width of {i} too big" if fit == "no_fit" else "",
            "source_url": f"https://ikea/{i}"}


def style(*ids):
    return {"category": "sofa", "style_text": "warm minimal", "detected_style": None, "source": SRC,
            "ranked": [{"id": i, "style_rank": n, "photo_rank": n, "photo_score": 0.1, "text_rank": n,
                        "text_score": 0.5} for n, i in enumerate(ids, 1)]}


class Pick(unittest.TestCase):
    def test_top_style_that_fits(self):
        r = pick([opt("kivik", "no_fit"), opt("gull", best=True), opt("glo")], style("kivik", "gull", "glo"))
        self.assertEqual(r["picked"]["id"], "gull")
        self.assertEqual([x["id"] for x in r["rejected"]], ["kivik"])
        self.assertEqual(r["rejected"][0]["status"], "no_fit")
        decisions = [a["decision"] for a in r["audit"]]
        self.assertEqual(decisions, ["ranked", "rejected", "picked"])
        self.assertIn("style #2 of 3", r["audit"][-1]["why"])
        self.assertIn("best value", r["audit"][-1]["why"])

    def test_budget(self):
        r = pick([opt("a", price=900), opt("b", price=300)], style("a", "b"), budget_usd=500)
        self.assertEqual(r["picked"]["id"], "b")
        self.assertIn("over budget: $900 > $500", r["rejected"][0]["why"])

    def test_nothing_fits(self):
        r = pick([opt("a", "no_fit")], style("a"))
        self.assertIsNone(r["picked"])
        self.assertEqual(r["audit"][-1]["decision"], "rejected")


if __name__ == "__main__":
    unittest.main()
