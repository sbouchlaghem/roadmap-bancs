import http.client
import os
import sys
import tempfile
import threading
import unittest

os.environ["ROADMAP_DATA"] = os.path.join(tempfile.mkdtemp(), "data")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import server  # noqa: E402


class Origine(unittest.TestCase):
    """Derrière Apache : seule la page du nom public (ROADMAP_HOTE) peut écrire."""

    @classmethod
    def setUpClass(cls):
        server.HOTE_PUBLIC = "testbench-roadmap.keas-group.com"
        cls.srv, _ = server.run(18765)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def post(self, origin):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1])
        c.request("POST", "/api/rien", body=b"{}", headers={"Origin": origin, "Content-Type": "application/json"})
        return c.getresponse().status

    def test_nom_public_accepte(self):
        self.assertNotEqual(self.post("https://testbench-roadmap.keas-group.com"), 403)

    def test_autre_site_refuse(self):
        self.assertEqual(self.post("https://pirate.example"), 403)

    def test_origin_vide_refuse(self):
        self.assertEqual(self.post("null"), 403)


if __name__ == "__main__":
    unittest.main()
