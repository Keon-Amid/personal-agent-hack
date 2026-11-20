"""Run: python3 -m unittest data.test_sie  (no network, no key)."""
import json
import unittest
from unittest import mock

from data import sie

PRODUCTS = [{"id": "a", "name": "A", "category": "sofa"}, {"id": "b", "name": "B", "category": "sofa"},
            {"id": "c", "name": "C", "category": "rug"}]
EMB = {"model": "m", "vectors": {"a": [1, 0], "b": [0.6, 0.8], "c": [1, 0]}}


class Rank(unittest.TestCase):
    def test_order_and_category(self):
        r = sie.rank(PRODUCTS, "sofa", [1, 0], EMB)
        self.assertEqual([o["id"] for o in r], ["a", "b"])
        self.assertEqual(r[0]["style_score"], 1.0)
        self.assertEqual(r[1]["style_score"], 0.6)
        self.assertEqual(r[0]["style_source"], {"kind": "superlinked", "model": "m"})

    def test_cosine_zero(self):
        self.assertEqual(sie.cosine([0, 0], [1, 1]), 0.0)


class Encode(unittest.TestCase):
    def test_parses_both_response_shapes(self):
        body = {"items": [{"dense": {"values": [1, 2]}}, {"dense": [3, 4]}]}
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = json.dumps(body).encode()
        with mock.patch.dict("os.environ", {"SIE_API_KEY": "sk-sie-test"}), \
                mock.patch("urllib.request.urlopen", return_value=resp) as u:
            self.assertEqual(sie.encode([{"text": "x"}, {"text": "y"}]), [[1, 2], [3, 4]])
            req = u.call_args[0][0]
            self.assertIn("/v1/encode/google%2Fsiglip-so400m-patch14-384", req.full_url)
            self.assertEqual(req.headers["Authorization"], "Bearer sk-sie-test")


class StyleMatch(unittest.TestCase):
    def test_fusion_and_sources(self):
        # photo ranks a > b; reranker ranks b > a by a lot; fused tie broken stably, both ranks recorded
        with mock.patch.object(sie, "query_text", return_value=[1, 0]), \
                mock.patch.object(sie, "score", return_value={"a": 0.1, "b": 0.9}):
            r = sie.style_match(PRODUCTS, "sofa", EMB, style_text="warm minimal")
        a = {o["id"]: o for o in r["ranked"]}
        self.assertEqual((a["a"]["photo_rank"], a["a"]["text_rank"]), (1, 2))
        self.assertEqual((a["b"]["photo_rank"], a["b"]["text_rank"]), (2, 1))
        self.assertEqual(a["a"]["style_fused"], a["b"]["style_fused"])
        self.assertEqual(r["source"]["rerank_model"], sie.RERANKER)
        self.assertIsNone(r["detected_style"])

    def test_room_photo_detects_style(self):
        with mock.patch.object(sie, "query_photo", return_value=[1, 0]), \
                mock.patch.object(sie, "encode", return_value=[[0, 1], [1, 0]]), \
                mock.patch.object(sie, "score", return_value={"a": 0.5, "b": 0.1}):
            r = sie.style_match(PRODUCTS, "sofa", EMB, room_photo=b"img")
        self.assertEqual(r["detected_style"][0]["style"], sie.STYLES[1])
        self.assertEqual(r["style_text"], f"{sie.STYLES[1]} style living room")
        self.assertEqual(r["ranked"][0]["id"], "a")

    def test_needs_input(self):
        with self.assertRaises(ValueError):
            sie.style_match(PRODUCTS, "sofa", EMB)


if __name__ == "__main__":
    unittest.main()
