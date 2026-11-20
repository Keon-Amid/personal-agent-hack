import json
import unittest
from pathlib import Path

from fit.checks import FITS, NO_FIT, overall
from fit.layout import add_product, check_layout, door_zone, find_spot, layout_from_scan, move
from fit.scan import load_scan

ROOT = Path(__file__).resolve().parent.parent
R = load_scan(ROOT / "assets/room_scan_roomplan.glb")
P = {p["id"]: p for p in json.loads((ROOT / "data/products.json").read_text())["products"]}
KIVIK = P["ikea-kivik-sofa-tibbleby-beige-gray-39440593"]


class Scan(unittest.TestCase):
    def test_room(self):
        self.assertEqual(len(R["walls"]), 6)
        self.assertEqual(len(R["outline"]), 6)  # L-shaped room
        d = R["doors"][0]
        self.assertAlmostEqual(d["width_in"], 32.0, delta=0.5)
        self.assertEqual(d["into_room"], [1, 0])
        cats = sorted(i["category"] for i in R["items"])
        self.assertEqual(cats, ["desk_chair", "dining_chair", "dining_chair", "table", "television"])

    def test_tv_is_wall_mounted(self):
        tv = next(i for i in R["items"] if i["category"] == "television")
        self.assertFalse(tv["on_floor"])


class Layout(unittest.TestCase):
    def test_scanned_layout_is_valid(self):
        res = check_layout(R, layout_from_scan(R))
        self.assertTrue(all(overall(rs) == FITS for rs in res.values()))

    def test_overlap_and_door(self):
        lay = add_product(layout_from_scan(R), KIVIK, 0, 50, 0)
        self.assertEqual(overall(check_layout(R, lay)[KIVIK["id"]]), NO_FIT)
        lay, res = move(R, lay, KIVIK["id"], -80, -40, 90)
        maths = " ".join(r["math"] for r in res[KIVIK["id"]])
        self.assertIn("door swing", maths)
        self.assertIn("outside the walls", maths)

    def test_find_spot_fits_everything(self):
        s = find_spot(R, layout_from_scan(R), KIVIK)
        self.assertIsNotNone(s)
        lay = add_product(layout_from_scan(R), KIVIK, s["x_in"], s["z_in"], s["rotation"])
        self.assertTrue(all(overall(rs) == FITS for rs in check_layout(R, lay).values()))

    def test_rug_under_furniture_but_off_walls(self):
        rug = P["ikea-jarnvag-rug-00623466"]
        s = find_spot(R, layout_from_scan(R), rug)
        self.assertIsNotNone(s)
        self.assertGreaterEqual(s["wall_gap_in"], 6)

    def test_door_zone_in_front_of_door(self):
        x0, z0, x1, z1 = door_zone(R["doors"][0])
        self.assertAlmostEqual(x1 - x0, 32.0, delta=0.5)
        self.assertGreater(x1, R["doors"][0]["center"][0])


if __name__ == "__main__":
    unittest.main()
