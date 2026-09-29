"""Cohérence du champ optionnel vigieau_zone de config/rivers.json."""
import json
import re
import unittest
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rivers.json"
ZONE_PATTERN = re.compile(r"^\d+_[0-9AB]{2,3}_\d{4}$")


def stations_with_zone():
    rivers = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["rivers"]
    return [
        (river["id"], station)
        for river in rivers
        for station in river["stations"]
        if "vigieau_zone" in station
    ]


class VigieauZoneConfigTest(unittest.TestCase):
    def test_zone_format(self):
        for river_id, station in stations_with_zone():
            with self.subTest(river=river_id, station=station["code"]):
                self.assertRegex(station["vigieau_zone"], ZONE_PATTERN)

    def test_zone_department_matches_station_department(self):
        for river_id, station in stations_with_zone():
            with self.subTest(river=river_id, station=station["code"]):
                zone_department = station["vigieau_zone"].split("_")[1]
                self.assertEqual(zone_department, station["dept"])


if __name__ == "__main__":
    unittest.main()
