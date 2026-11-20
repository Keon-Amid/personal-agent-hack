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

    def test_new_piece_too_close_is_unsure(self):
        table = next(i for i in R["items"] if i["category"] == "table")
        ost = P["ikea-ostavall-adjustable-coffee-table-black-35-3-8-40534152"]
        left_edge = table["x_in"] - table["w_in"] / 2
        lay = add_product(layout_from_scan(R), ost, left_edge - ost["dims_in"]["w"] / 2 - 4.6, table["z_in"], 0)
        res = check_layout(R, lay)[ost["id"]]
        sp = [r for r in res if r["check"] == "spacing"]
        self.assertTrue(sp and sp[0]["verdict"] == "unsure")
        self.assertIn("4.6 in from table_other_rect", sp[0]["math"])

    def test_corner_on_wall_line_counts_inside(self):
        poang = P["ikea-poang-armchair-birch-veneer-knisa-light-beige-59305928"]
        wall_z = min(p[1] for p in R["outline"])
        lay = add_product(layout_from_scan(R), poang, -27.6, wall_z + poang["dims_in"]["d"] / 2, 0)
        r = [x for x in check_layout(R, lay)[poang["id"]] if x["check"] == "in_room"][0]
        self.assertEqual(r["verdict"], FITS)

    def test_whole_plan_places_and_fits(self):
        plan = json.loads((ROOT / "contracts/plan.room_scan.json").read_text())
        lay = layout_from_scan(R)
        for it in sorted(plan["items"], key=lambda i: P[i["product_id"]]["category"] == "rug"):
            s = find_spot(R, lay, P[it["product_id"]])
            self.assertIsNotNone(s, it["product_id"])
            lay = add_product(lay, P[it["product_id"]], s["x_in"], s["z_in"], s["rotation"])
        self.assertTrue(all(overall(rs) == FITS for rs in check_layout(R, lay).values()))

    def test_tv_moves_along_a_wall_but_not_into_the_room(self):
        lay = layout_from_scan(R)
        tv = next(i for i in lay if i["category"] == "television")
        _, res = move(R, lay, tv["id"], tv["x_in"], tv["z_in"] - 30)  # slide along its wall
        self.assertEqual(res[tv["id"]][0]["verdict"], FITS)
        _, res = move(R, lay, tv["id"], 0, 0)  # middle of the room
        self.assertEqual(res[tv["id"]][0]["verdict"], NO_FIT)
        self.assertIn("from the nearest wall", res[tv["id"]][0]["math"])

    def test_new_piece_kept_out_of_the_way_in(self):
        door = R["doors"][0]
        lamp = P["ikea-barlast-floor-lamp-black-white-59-70437814"]
        x, z = door["center"][0] + door["into_room"][0] * 20, door["center"][1]
        res = check_layout(R, add_product(layout_from_scan(R), lamp, x, z, 0))[lamp["id"]]
        self.assertTrue(any(r["check"] == "door_path" and r["verdict"] == NO_FIT for r in res))


if __name__ == "__main__":
    unittest.main()
