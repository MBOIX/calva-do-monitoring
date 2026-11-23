"""Exclusion des analyses hors colonne d'eau (sédiments…) dans l'ETL qualité."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fetch_quality_data.py"
_spec = importlib.util.spec_from_file_location("fetch_quality_data", SCRIPT_PATH)
fetch_quality_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_quality_data)

FRACTION_LABELS = {
    "23": "Eau brute",
    "3": "Phase aqueuse de l'eau (filtrée, centrifugée...)",
    "31": "Sédiments bruts",
    "32": "Particule < 2 mm de sédiments",
}
AMMONIUM = "1335"
STATION = {"code": "03246000", "name": "LA SEULLES A COURSEULLES 1"}


def analysis(date, value, fraction):
    return {
        "date_prelevement": date,
        "resultat": value,
        "code_fraction": fraction,
        "libelle_fraction": FRACTION_LABELS.get(fraction),
    }


def silently(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


class IsWaterAnalysisTest(unittest.TestCase):
    def test_accepts_water_fractions(self):
        for fraction in ("23", "3"):
            with self.subTest(fraction=fraction):
                self.assertTrue(fetch_quality_data.is_water_analysis(analysis("2026-08-20", 0.07, fraction)))

    def test_rejects_sediment_fractions(self):
        for fraction in ("31", "32"):
            with self.subTest(fraction=fraction):
                self.assertFalse(fetch_quality_data.is_water_analysis(analysis("2026-08-20", 66.7, fraction)))

    def test_rejects_analysis_without_fraction(self):
        raw = {"date_prelevement": "2026-08-20", "resultat": 0.07}

        self.assertFalse(fetch_quality_data.is_water_analysis(raw))


class KeepWaterAnalysesTest(unittest.TestCase):
    def test_keeps_only_water_analyses_in_original_order(self):
        raw_records = [
            analysis("2026-07-21", 0.03, "3"),
            analysis("2026-08-20", 66.7, "32"),
            analysis("2026-08-20", 0.07, "23"),
        ]

        kept = silently(fetch_quality_data.keep_water_analyses, raw_records)

        self.assertEqual([r["resultat"] for r in kept], [0.03, 0.07])

    def test_returns_empty_list_for_empty_input(self):
        self.assertEqual(silently(fetch_quality_data.keep_water_analyses, []), [])

    def test_logs_each_ignored_fraction_with_its_count(self):
        raw_records = [
            analysis("2025-08-07", 66.7, "32"),
            analysis("2026-08-20", 66.7, "32"),
            {"date_prelevement": "2026-08-21", "resultat": 1.0},
        ]
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            fetch_quality_data.keep_water_analyses(raw_records)

        self.assertIn("Ignored 2 analyses on non-water fraction: Particule < 2 mm de sédiments", output.getvalue())
        self.assertIn("Ignored 1 analyses on non-water fraction: unknown", output.getvalue())


class FetchStationQualityIntegrationTest(unittest.TestCase):
    """fetch_station_quality : API simulée → fichier de cache réellement écrit sur disque."""

    def setUp(self):
        self.cache_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cache_file = self.cache_dir / f"{STATION['code']}_quality.json"

    def fetch_with_api_returning(self, ammonium_raw_records):
        def fake_fetch(station_code, param_code, date_start=None):
            return ammonium_raw_records if param_code == AMMONIUM else []

        with mock.patch.object(fetch_quality_data, "fetch_parameter_records", side_effect=fake_fetch):
            silently(fetch_quality_data.fetch_station_quality, STATION, str(self.cache_dir))
        return json.loads(self.cache_file.read_text(encoding="utf-8"))["parameters"][AMMONIUM]

    def test_first_fetch_caches_water_analyses_only(self):
        ammonium = self.fetch_with_api_returning([
            analysis("2026-08-20", 66.7, "32"),
            analysis("2026-08-20", 0.07, "3"),
        ])

        self.assertEqual(ammonium["records"], [{"date": "2026-08-20", "value": 0.07}])
        self.assertEqual(ammonium["record_count"], 1)

    def test_incremental_fetch_does_not_merge_sediment_analyses(self):
        self.fetch_with_api_returning([analysis("2026-07-21", 0.03, "3")])

        ammonium = self.fetch_with_api_returning([
            analysis("2026-07-21", 0.03, "3"),
            analysis("2026-08-20", 66.7, "32"),
        ])

        self.assertEqual(ammonium["records"], [{"date": "2026-07-21", "value": 0.03}])
        self.assertEqual(ammonium["date_max"], "2026-07-21")


if __name__ == "__main__":
    unittest.main()
