"""Tests for agent/senso.py. Offline with a fake HTTP layer; LIVE=1 (+ SENSO_API_KEY) also hits Senso."""
import os
import tempfile
import unittest

from agent import senso

KIVIK = {"slot": "sofa", "product_id": "ikea-kivik-sofa-grann-bomstad-black-80519531",
         "name": "KIVIK Sofa - Grann/Bomstad black", "price_usd": 1299.0,
         "dims_in": {"w": 89.375, "d": 37.375, "h": 32.625}}

RUN_DONE = {"eval_run_id": "run-1", "status": "completed", "accuracy_pct": 50,
            "claims": [{"claim_text": "KIVIK is 89.375 inches wide.", "verdict": "verified",
                        "quote": "Size: width 89.375 in"},
                       {"claim_text": "36 in walkway.", "verdict": "unsupported", "quote": None,
                        "evidence": [{"content": "Walkway: keep at least 36 inches"}]}]}


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        return self.responses.pop(0)


class SensoOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = os.environ.get("ROOM_FURNISHER_SENSO_CACHE")
        os.environ["ROOM_FURNISHER_SENSO_CACHE"] = self.tmp.name
        self._http, self._sleep = senso._http, senso._sleep
        self.slept = []
        senso._sleep = self.slept.append

    def tearDown(self):
        senso._http, senso._sleep = self._http, self._sleep
        if self._env is None:
            os.environ.pop("ROOM_FURNISHER_SENSO_CACHE", None)
        else:
            os.environ["ROOM_FURNISHER_SENSO_CACHE"] = self._env
        self.tmp.cleanup()

    def test_check_parses_and_caches(self):
        fake = senso._http = FakeHTTP([(200, RUN_DONE)])
        c = senso.check("text", "q")
        self.assertEqual(c["check_id"], "run-1")
        self.assertEqual(c["accuracy_pct"], 50.0)
        self.assertFalse(c["cached"])
        self.assertEqual(c["claims"][0], {"claim": "KIVIK is 89.375 inches wide.", "verdict": "verified",
                                          "quote": "Size: width 89.375 in"})
        self.assertEqual(c["claims"][1]["quote"], "Walkway: keep at least 36 inches")  # evidence fallback
        method, path, body = fake.calls[0]
        self.assertEqual((method, path), ("POST", "/org/evals/text"))
        self.assertEqual(body, {"text": "text", "author": "ai_assistant", "question": "q", "wait": True})
        again = senso.check("text", "q")
        self.assertTrue(again["cached"])
        self.assertEqual(again["claims"], c["claims"])
        self.assertEqual(len(fake.calls), 1)  # served from disk

    def test_polls_until_claims(self):
        fake = senso._http = FakeHTTP([(202, {"eval_run_id": "run-1", "status": "running", "claims": []}),
                                       (200, {"eval_run_id": "run-1", "status": "running"}),
                                       (200, RUN_DONE)])
        c = senso.check("t2", "q")
        self.assertEqual(len(c["claims"]), 2)
        self.assertEqual([p for _, p, _ in fake.calls[1:]], ["/org/evals/runs/run-1"] * 2)
        self.assertEqual(self.slept, [5, 5])

    def test_poll_gives_up_after_60s(self):
        pending = (200, {"eval_run_id": "run-1", "status": "running"})
        senso._http = FakeHTTP([pending] * 20)
        with self.assertRaises(senso.SensoError):
            senso.check("t3", "q")
        self.assertEqual(sum(self.slept), 60)

    def test_http_error_raises_and_does_not_cache(self):
        senso._http = FakeHTTP([(403, {"message": "error code: 1010"})])
        with self.assertRaises(senso.SensoError):
            senso.check("t4", "q")
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_build_claim_sofa(self):
        s = senso.build_claim(KIVIK)
        self.assertIn("The KIVIK Sofa - Grann/Bomstad black is 89.375 inches wide.", s)
        self.assertIn("ships in 2 boxes: 36.5 x 72 x 22.5 inches; 35.5 x 37.75 x 11 inches", s)
        self.assertIn("$1299", s)
        self.assertIn(senso.RULE_WALKWAY, s)
        self.assertIn(senso.RULE_DOORWAY, s)
        self.assertIn(senso.RULE_SOFA_WALL, s)
        self.assertNotIn("wall is", s)  # no room arithmetic

    def test_build_claim_rug_and_null_price(self):
        s = senso.build_claim({"slot": "rug", "product_id": "nope", "name": "LOHALS Rug", "price_usd": None,
                               "dims_in": {"w": 63, "d": 91, "h": None}})
        self.assertIn("63 inches wide and 91 inches long", s)
        self.assertIn(senso.RULE_RUG, s)
        self.assertNotIn("$", s)
        self.assertNotIn("ships", s)

    def test_verdict_ok(self):
        v = lambda *vs: {"claims": [{"claim": "", "verdict": x, "quote": None} for x in vs]}
        self.assertTrue(senso.verdict_ok(v("verified", "unsupported", "not_verifiable")))
        self.assertFalse(senso.verdict_ok(v("verified", "conflict")))
        self.assertFalse(senso.verdict_ok(v("unsupported")))
        self.assertFalse(senso.verdict_ok(v()))
        self.assertFalse(senso.verdict_ok(None))


@unittest.skipUnless(os.environ.get("LIVE") == "1", "LIVE=1 to call Senso")
class SensoLive(unittest.TestCase):
    def test_rule_claim_verified_with_quote(self):
        os.environ["ROOM_FURNISHER_SENSO_CACHE"] = tempfile.mkdtemp()  # force a real call
        c = senso.check(senso.RULE_WALKWAY, "What clearance do the room rules require?")
        print("\nLIVE senso:", c)
        self.assertTrue(c["check_id"])
        hit = [x for x in c["claims"] if x["verdict"] == "verified" and x["quote"]]
        self.assertTrue(hit, c)
        self.assertIn("36", hit[0]["quote"])

    def test_kivik_claim(self):
        c = senso.check(senso.build_claim(KIVIK), "Does the KIVIK sofa meet the room rules?")
        print("\nLIVE kivik:", c)
        self.assertTrue(senso.verdict_ok(c), c)


if __name__ == "__main__":
    unittest.main()
