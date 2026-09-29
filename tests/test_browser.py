"""Enveloppe unittest du lanceur de pages de tests navigateur."""
import unittest

from tests import run_browser_tests as runner


@unittest.skipIf(
    runner.find_chrome() is None,
    "Chrome introuvable : définir $CHROME_BIN pour exécuter les tests navigateur",
)
class BrowserPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = runner.find_chrome()
        cls._server = runner.serve_repository()
        cls.port = cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)

    def assert_page_passes(self, page):
        status, detail = runner.run_page(self.chrome, self.port, page)
        self.assertEqual(status, "pass", f"{page}\n{detail}")

    def test_situation_unit(self):
        self.assert_page_passes("tests/situation.test.html")

    def test_vigieau_unit(self):
        self.assert_page_passes("tests/vigieau.test.html")

    def test_situation_integration(self):
        self.assert_page_passes("tests/situation.integration.test.html")

    def test_smoke(self):
        self.assert_page_passes("tests/smoke.test.html")


class ParseReportTest(unittest.TestCase):
    def test_pass_status_is_parsed(self):
        dom = '<pre id="test-results" data-status="pass">3 ok</pre>'
        self.assertEqual(runner.parse_report(dom), ("pass", "3 ok"))

    def test_fail_status_keeps_details(self):
        dom = '<pre id="test-results" data-status="fail">FAIL a</pre>'
        self.assertEqual(runner.parse_report(dom), ("fail", "FAIL a"))

    def test_missing_report_is_flagged(self):
        status, _ = runner.parse_report("<html></html>")
        self.assertEqual(status, "missing")

    def test_report_without_status_is_flagged(self):
        status, _ = runner.parse_report('<pre id="test-results">x</pre>')
        self.assertEqual(status, "missing")


if __name__ == "__main__":
    unittest.main()
