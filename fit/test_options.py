import unittest

from fit import measurement
from fit.options import options, room

RM = room(measurement(88), measurement(140), measurement(30), measurement(80))


def prod(i, price, rating, reviews, w=60):
    return {"id": i, "name": f"{i} - x", "category": "sofa", "price_usd": price, "rating": rating,
            "review_count": reviews, "dims_in": {"w": w, "d": 30, "h": 30},
            "packages_in": [{"w": 20, "d": 60, "h": 20}], "source_url": "u"}


class Options(unittest.TestCase):
    def test_frontier(self):
        ps = [prod("cheap", 100, 4.0, 50), prod("good", 300, 4.6, 50),
              prod("worse", 400, 4.2, 50), prod("best", 900, 4.8, 50)]
        o = {x["id"]: x for x in options(ps, "sofa", RM)}
        self.assertTrue(o["cheap"]["best_value"])
        self.assertTrue(o["good"]["best_value"])
        self.assertTrue(o["best"]["best_value"])
        self.assertFalse(o["worse"]["best_value"])
        self.assertIn("good is $300", o["worse"]["why"])

    def test_too_wide_never_best_value(self):
        ps = [prod("wide", 50, 5.0, 999, w=95), prod("ok", 500, 4.0, 50)]
        o = {x["id"]: x for x in options(ps, "sofa", RM)}
        self.assertEqual(o["wide"]["fit"], "no_fit")
        self.assertFalse(o["wide"]["best_value"])
        self.assertTrue(o["wide"]["why"].startswith("no_fit: width 95 in > 88 in"))
        self.assertTrue(o["ok"]["best_value"])  # the wide one doesn't beat it

    def test_few_reviews_not_ranked(self):
        ps = [prod("new", 100, 5.0, 3), prod("ok", 500, 4.0, 50)]
        o = {x["id"]: x for x in options(ps, "sofa", RM)}
        self.assertFalse(o["new"]["best_value"])
        self.assertIn("3 reviews", o["new"]["why"])
        self.assertTrue(o["ok"]["best_value"])

    def test_no_price(self):
        o = options([prod("np", None, 4.5, 50)], "sofa", RM)[0]
        self.assertIn("no price", o["why"])


if __name__ == "__main__":
    unittest.main()
