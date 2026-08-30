import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from countries.data import (
    CountryDataError,
    load_capital_data,
    load_country_data,
    validate_capital_data,
    validate_country_data,
)


class CountryDataTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.metadata_path = settings.BASE_DIR / "data" / "countries.json"
        cls.geometry_path = settings.BASE_DIR / "static" / "data" / "countries.geojson"
        cls.capital_path = settings.BASE_DIR / "static" / "data" / "capitals.geojson"
        with cls.metadata_path.open(encoding="utf-8") as metadata_file:
            cls.metadata = json.load(metadata_file)
        with cls.geometry_path.open(encoding="utf-8") as geometry_file:
            cls.geometry = json.load(geometry_file)
        with cls.capital_path.open(encoding="utf-8") as capital_file:
            cls.capitals = json.load(capital_file)

    def test_bundled_country_schema_is_valid(self):
        metadata, geometry = load_country_data()

        self.assertEqual(len(metadata["countries"]), 238)
        self.assertEqual(len(geometry["features"]), 238)
        self.assertEqual(metadata["source"]["dataset_version"], "5.1.1")

    def test_iso_alpha_2_codes_are_valid_and_unique(self):
        codes = [country["iso_a2"] for country in self.metadata["countries"]]

        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(code) == 2 and code.isascii() and code.isupper() for code in codes))
        self.assertNotIn("XK", codes)

    def test_geometry_and_metadata_join_exactly(self):
        metadata_codes = {country["iso_a2"] for country in self.metadata["countries"]}
        geometry_codes = {feature["properties"]["iso_a2"] for feature in self.geometry["features"]}

        self.assertSetEqual(metadata_codes, geometry_codes)
        self.assertIn("RO", geometry_codes)
        self.assertTrue(next(country for country in self.metadata["countries"] if country["iso_a2"] == "VA")["small"])

    def test_missing_country_files_are_rejected(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with self.assertRaisesRegex(CountryDataError, "Could not read valid country data"):
                load_country_data(missing, missing)

    def test_invalid_country_record_is_rejected(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["countries"][0]["iso_a2"] = "INVALID"

        with self.assertRaisesRegex(CountryDataError, "invalid ISO alpha-2"):
            validate_country_data(metadata, self.geometry)

    def test_geometry_metadata_mismatch_is_rejected(self):
        geometry = copy.deepcopy(self.geometry)
        geometry["features"][0]["id"] = "ZZ"

        with self.assertRaisesRegex(CountryDataError, "invalid identity"):
            validate_country_data(self.metadata, geometry)

    def test_country_metadata_route_serves_canonical_file(self):
        response = self.client.get(reverse("countries:metadata"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["Cache-Control"], "public, max-age=86400")

    def test_bundled_capital_schema_and_country_joins_are_valid(self):
        capital_data = load_capital_data(self.metadata)
        country_codes = {country["iso_a2"] for country in self.metadata["countries"]}

        self.assertEqual(len(capital_data["features"]), 198)
        self.assertEqual(
            len({feature["properties"]["iso_a2"] for feature in capital_data["features"]}),
            194,
        )
        self.assertTrue(
            all(feature["properties"]["iso_a2"] in country_codes for feature in capital_data["features"])
        )
        self.assertEqual(capital_data["source"]["dataset_version"], "5.1.2")

    def test_capital_ids_coordinates_and_names_are_valid(self):
        feature_ids = [feature["id"] for feature in self.capitals["features"]]

        self.assertEqual(len(feature_ids), len(set(feature_ids)))
        self.assertTrue(all(feature_id.startswith("ne-") for feature_id in feature_ids))
        self.assertTrue(
            all("\ufffd" not in feature["properties"]["name"] for feature in self.capitals["features"])
        )

    def test_legitimate_multiple_capitals_are_preserved(self):
        capital_counts = {
            code: sum(
                feature["properties"]["iso_a2"] == code
                for feature in self.capitals["features"]
            )
            for code in ("BO", "CI", "ZA")
        }

        self.assertEqual(capital_counts, {"BO": 2, "CI": 2, "ZA": 3})

    def test_capital_without_canonical_join_is_rejected(self):
        capitals = copy.deepcopy(self.capitals)
        capitals["features"][0]["properties"]["iso_a2"] = "XK"

        with self.assertRaisesRegex(CountryDataError, "no canonical country join"):
            validate_capital_data(
                capitals, {country["iso_a2"] for country in self.metadata["countries"]}
            )