import json
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from agent import server, store


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()

    def req(self, method, path, body=None):
        r = urllib.request.Request(self.base + path, method=method,
                                   data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read() or b"{}"), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_post_returns_id_then_get_polls_to_done(self):
        def fake_run_agent(room, plan_id=None, **kw):
            store.new_plan(plan_id=plan_id)
            time.sleep(0.2)
        with mock.patch("agent.agent.run_agent", side_effect=fake_run_agent):
            code, out, hdr = self.req("POST", "/api/plan", {"room": {"wall": 88, "depth": 150, "door_width": 30,
                                                                     "door_height": 80}, "style_text": "warm minimal"})
            self.assertEqual(code, 202)
            self.assertEqual(hdr["Access-Control-Allow-Origin"], server.ORIGIN)
            pid = out["plan_id"]
            code, plan, _ = self.req("GET", f"/api/plan/{pid}")
            self.assertEqual((code, plan["status"]), (200, "running"))
            for _ in range(50):
                time.sleep(0.05)
                plan = self.req("GET", f"/api/plan/{pid}")[1]
                if plan["status"] != "running":
                    break
            self.assertEqual(plan["status"], "done")
            self.assertNotIn("state", plan)
            self.assertIn("audit", plan)

    def test_errors(self):
        self.assertEqual(self.req("POST", "/api/plan", {"room": {"wall": 88}})[0], 400)
        self.assertEqual(self.req("GET", "/api/plan/doesnotexist")[0], 404)
        self.assertEqual(self.req("GET", "/api/health")[1], {"ok": True})


if __name__ == "__main__":
    unittest.main()
