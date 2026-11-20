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


if __name__ == "__main__":
    unittest.main()
