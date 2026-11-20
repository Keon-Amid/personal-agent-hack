"""Offline tests for agent.room (HTTP mocked). Live: LIVE=1 with SIE_API_KEY and contracts/demo_room.jpg."""
import io
import json
import os
import struct
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from agent import room

ROOT = Path(__file__).resolve().parent.parent


def png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"


def jpeg(w, h):
    sof = b"\xff\xc0" + struct.pack(">HBHH", 11, 8, h, w) + b"\x03\x01\x22\x00"
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"JF" + sof + b"\xff\xd9"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def respond(objects):
    return FakeResp(json.dumps({"model": "m", "items": [{"objects": objects}]}).encode())


DOOR = {"label": "door", "score": 0.8, "bbox": [500, 100, 150, 400]}   # 400 px tall -> 0.2 in/px
WALL = {"label": "wall", "score": 0.7, "bbox": [0, 0, 440, 600]}       # 440 px -> 88 in


class EstimateTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch("data.sie._key", return_value="sk-sie-test")
        p.start()
        self.addCleanup(p.stop)

    def run_est(self, objects, photo=None, exact=None):
        with mock.patch("agent.room.urllib.request.urlopen", return_value=respond(objects)) as u:
            out = room.estimate(photo or png(1000, 600), exact)
        return out, u

    def test_image_size(self):
        self.assertEqual(room.image_size(png(1000, 600)), (1000, 600))
        self.assertEqual(room.image_size(jpeg(1024, 768)), (1024, 768))
        self.assertIsNone(room.image_size(b"nope"))

    def test_photo_estimate_scale_and_audit(self):
        (rm, recs), u = self.run_est([DOOR, WALL])
        req = u.call_args[0][0]
        self.assertIn("/v1/extract/IDEA-Research%2Fgrounding-dino-base", req.full_url)
        self.assertEqual(json.loads(req.data)["params"]["labels"], ["door", "wall", "floor"])
        self.assertTrue(req.get_header("User-agent"))
        self.assertEqual(rm["wall"], {"value_in": 88.0, "error_in": 8.8, "source": "estimated:door"})
        self.assertEqual(rm["door_width"]["value_in"], 30.0)
        self.assertEqual(rm["door_height"]["value_in"], 80.0)
        self.assertEqual(rm["depth"]["source"], "estimated:default")
        self.assertEqual(rm["depth"]["error_in"], 36.0)
        photo = recs[0]
        self.assertEqual(photo["step"], "estimate_room")
        self.assertEqual(photo["source"]["kind"], "superlinked")
        self.assertEqual(photo["source"]["inches_per_px"], 0.2)
        self.assertEqual(photo["source"]["door_box"], [500, 100, 150, 400])
        self.assertIn("ts", photo)
        self.assertIn("depth", recs[1]["why"])
        self.assertIn("25%", recs[1]["why"])

    def test_cut_off_door_doubles_error(self):
        cut = {"label": "door", "score": 0.8, "bbox": [500, 200, 150, 400]}  # bottom at 600 = image edge
        (rm, recs), _ = self.run_est([cut, WALL])
        self.assertEqual(rm["wall"]["error_in"], 17.6)
        self.assertTrue(recs[0]["source"]["door_cut_off"])
        self.assertIn("cut off", recs[0]["why"])

    def test_xyxy_box_detected(self):
        door = {"label": "door", "score": 0.8, "bbox": [500, 100, 650, 500]}  # xywh would overrun 600 px
        (rm, recs), _ = self.run_est([door, WALL])
        self.assertEqual(recs[0]["source"]["bbox_format"], "xyxy")
        self.assertEqual(rm["door_width"]["value_in"], 30.0)

    def test_no_wall_box_uses_photo_width(self):
        (rm, recs), _ = self.run_est([DOOR])
        self.assertEqual(rm["wall"]["value_in"], 200.0)
        self.assertEqual(rm["wall"]["error_in"], 50.0)
        self.assertIn("no wall box", recs[0]["why"])

    def test_exact_overrides_key_by_key(self):
        (rm, recs), _ = self.run_est([DOOR, WALL], exact={"wall": 88, "depth": 150})
        self.assertEqual(rm["wall"], {"value_in": 88.0, "error_in": 0.0, "source": "user"})
        self.assertEqual(rm["depth"]["source"], "user")
        self.assertEqual(rm["door_width"]["source"], "estimated:door")
        self.assertNotIn("depth", recs[0]["decision"])
        self.assertEqual(recs[-1]["status"], "exact")

    def test_all_exact_makes_no_call(self):
        ex = {"wall": 88, "depth": 150, "door_width": 30, "door_height": 80}
        (rm, recs), u = self.run_est([DOOR], exact=ex)
        u.assert_not_called()
        self.assertTrue(all(m["source"] == "user" and m["error_in"] == 0 for m in rm.values()))

    def test_no_photo_no_exact_names_missing(self):
        with self.assertRaises(ValueError) as cm:
            room.estimate()
        for k in room.KEYS:
            self.assertIn(k, str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            room.estimate(exact={"wall": 88, "depth": 150})
        self.assertIn("door_width", str(cm.exception))
        self.assertNotIn("wall", str(cm.exception).split(":")[-1])

    def test_no_photo_missing_only_depth_uses_default(self):
        rm, recs = room.estimate(exact={"wall": 88, "door_width": 30, "door_height": 80})
        self.assertEqual(rm["depth"]["source"], "estimated:default")

    def test_http_error_reported_and_exact_required(self):
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"detail":"model not found"}'))
        with mock.patch("agent.room.urllib.request.urlopen", side_effect=err) as u:
            with self.assertRaises(ValueError) as cm:
                room.estimate(png(1000, 600))
        self.assertEqual(u.call_count, 2)  # grounding-dino, then owlv2
        msg = str(cm.exception)
        self.assertIn("HTTP 404", msg)
        self.assertIn("model not found", msg)
        self.assertIn("wall", msg)

    def test_fallback_model(self):
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"nope"))
        with mock.patch("agent.room.urllib.request.urlopen", side_effect=[err, respond([DOOR, WALL])]):
            rm, recs = room.estimate(png(1000, 600))
        self.assertEqual(recs[0]["source"]["model"], "google/owlv2-base-patch16-ensemble")

    def test_no_door_found(self):
        with self.assertRaises(ValueError) as cm:
            self.run_est([WALL])
        self.assertIn("no door", str(cm.exception))

    def test_missing_key(self):
        with mock.patch("data.sie._key", side_effect=SystemExit("SIE_API_KEY is not set (put it in .env)")):
            with self.assertRaises(ValueError) as cm:
                room.estimate(png(1000, 600))
        self.assertIn("SIE_API_KEY", str(cm.exception))

    def test_estimated_wall_feeds_fit(self):
        from fit.options import options
        products = json.loads((ROOT / "data/products.json").read_text())["products"]
        (rm, _), _ = self.run_est([DOOR, WALL])
        verdicts = {o["fit"] for o in options(products, "sofa", rm)}
        self.assertIn("unsure", verdicts)


@unittest.skipUnless(os.environ.get("LIVE") == "1", "LIVE=1 only")
class LiveTest(unittest.TestCase):
    def test_live_demo_room(self):
        photo = ROOT / "contracts/demo_room.jpg"
        if not photo.exists():
            self.skipTest("contracts/demo_room.jpg missing")
        try:
            from data import sie
            sie._key()
        except SystemExit:
            self.skipTest("SIE_API_KEY not set")
        rm, recs = room.estimate(photo.read_bytes())
        print(json.dumps({"room": rm, "audit": recs}, indent=1))
        self.assertEqual(recs[0]["source"]["kind"], "superlinked")
        self.assertGreater(rm["wall"]["value_in"], 0)


if __name__ == "__main__":
    unittest.main()
