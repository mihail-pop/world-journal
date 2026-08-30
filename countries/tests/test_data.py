import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from countries.data import CountryDataError, load_country_data, validate_country_data


class CountryDataTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.metadata_path = settings.BASE_DIR / "data" / "countries.json"
        cls.geometry_path = settings.BASE_DIR / "static" / "data" / "countries.geojson"
        with cls.metadata_path.open(encoding="utf-8") as metadata_file:
            cls.metadata = json.load(metadata_file)
        with cls.geometry_path.open(encoding="utf-8") as geometry_file:
            cls.geometry = json.load(geometry_file)

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