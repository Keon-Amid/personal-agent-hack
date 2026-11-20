"""Run: python3 -m unittest discover -s fit -t ."""
import unittest

from fit import FITS, NO_FIT, UNSURE, check_doorway, check_floor, check_wall, measurement, overall

SOFA = {"dims_in": {"w": 84, "d": 38, "h": 32}}


class Wall(unittest.TestCase):
    def test_fits_exact_measurement(self):
        r = check_wall(SOFA, measurement(88))
        self.assertEqual(r["verdict"], FITS)
        self.assertEqual(r["margin_in"], 4)
        self.assertIn("84 in", r["math"])

    def test_too_wide_is_negative_control(self):
        r = check_wall({"dims_in": {"w": 91, "d": 38, "h": 32}}, measurement(88))
        self.assertEqual(r["verdict"], NO_FIT)
        self.assertEqual(r["margin_in"], -3)  # "3 inches too wide"

    def test_estimate_close_call_is_unsure(self):
        r = check_wall(SOFA, measurement(86, 6, "estimated:door"))
        self.assertEqual(r["verdict"], UNSURE)
        self.assertIn("±6", r["math"])
        self.assertIn("estimated:door", r["math"])

    def test_clearance_counts(self):
        self.assertEqual(check_wall(SOFA, measurement(88), clearance_in=6)["verdict"], NO_FIT)

    def test_exactly_equal_fits(self):
        self.assertEqual(check_wall(SOFA, measurement(84))["verdict"], FITS)


class Floor(unittest.TestCase):
    def test_walkway(self):
        self.assertEqual(check_floor(SOFA, measurement(80))["verdict"], FITS)   # 38+36=74
        self.assertEqual(check_floor(SOFA, measurement(70))["verdict"], NO_FIT)


class Doorway(unittest.TestCase):
    def test_flat_pack_boxes(self):
        item = {"dims_in": {"w": 84, "d": 38, "h": 32},
                "packages_in": [{"w": 40, "d": 30, "h": 12}, {"w": 90, "d": 20, "h": 10}]}
        rs = check_doorway(item, measurement(30), measurement(80))
        self.assertEqual(len(rs), 4)
        self.assertEqual(overall(rs), FITS)

    def test_assembled_too_big(self):
        item = {"dims_in": {"w": 84, "d": 38, "h": 36}}  # smallest side 36 > 30 in door
        rs = check_doorway(item, measurement(30), measurement(80))
        self.assertEqual(overall(rs), NO_FIT)
        self.assertIn("assembled item", rs[0]["math"])


class Measurement(unittest.TestCase):
    def test_rejects_bad(self):
        with self.assertRaises(ValueError):
            measurement(0)
        with self.assertRaises(ValueError):
            measurement(10, -1)


class Overall(unittest.TestCase):
    def test_worst_wins(self):
        mk = lambda v: {"verdict": v}  # noqa: E731
        self.assertEqual(overall([mk(FITS), mk(UNSURE)]), UNSURE)
        self.assertEqual(overall([mk(UNSURE), mk(NO_FIT)]), NO_FIT)
        self.assertEqual(overall([mk(FITS)]), FITS)


if __name__ == "__main__":
    unittest.main()
