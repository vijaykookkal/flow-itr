"""The local server refuses every page but its own.

Runs the real server on a spare port, in a throwaway Flow home, and asks it
things the way a hostile page would: under another host name (DNS rebinding),
without the token, and from another origin.
"""

from __future__ import annotations

import http.client
import os
import tempfile
import threading
import unittest

_HOME = tempfile.mkdtemp(prefix="flow-test-home-")
os.environ["FLOW_HOME"] = _HOME

from server import app  # noqa: E402  (after FLOW_HOME, so nothing touches the real home)


class ServerGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = app.Server(("127.0.0.1", 0), app.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def ask(self, method, path, host=None, token=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host or f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if token:
            headers["X-ITR-Token"] = token
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        conn.close()
        return resp.status, body

    def test_the_page_and_its_token_are_served_to_its_own_host(self):
        status, body = self.ask("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(app.TOKEN, body)
        status, _ = self.ask("GET", "/", host=f"localhost:{self.port}")
        self.assertEqual(status, 200)

    def test_another_host_name_gets_nothing(self):
        # DNS rebinding: the request reaches 127.0.0.1 but names the other site.
        status, body = self.ask("GET", "/", host=f"attacker.example:{self.port}")
        self.assertEqual(status, 421)
        self.assertNotIn(app.TOKEN, body)
        status, _ = self.ask("GET", "/api/version", host=f"attacker.example:{self.port}", token=app.TOKEN)
        self.assertEqual(status, 421)

    def test_the_api_needs_the_token(self):
        self.assertEqual(self.ask("GET", "/api/version")[0], 403)
        self.assertEqual(self.ask("GET", "/api/version", token="not-the-token")[0], 403)
        self.assertEqual(self.ask("GET", "/api/version", token=app.TOKEN)[0], 200)

    def test_another_origin_is_refused_on_reads_and_writes(self):
        evil = "http://attacker.example"
        self.assertEqual(self.ask("GET", "/api/version", token=app.TOKEN, origin=evil)[0], 403)
        self.assertEqual(self.ask("POST", "/api/stop", token=app.TOKEN, origin=evil)[0], 403)
        own = f"http://localhost:{self.port}"
        self.assertEqual(self.ask("GET", "/api/version", token=app.TOKEN, origin=own)[0], 200)


if __name__ == "__main__":
    unittest.main()
