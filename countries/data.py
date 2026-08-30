from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings


EXPECTED_COUNTRY_COUNT = 238
COUNTRY_FIELDS = {
    "iso_a2",
    "iso_a3",
    "name",
    "region",
    "subregion",
    "centroid",
    "bounds",
    "flag",
    "small",
}
ALPHA_2_PATTERN = re.compile(r"^[A-Z]{2}$")
ALPHA_3_PATTERN = re.compile(r"^[A-Z]{3}$")


class CountryDataError(ValueError):
    pass


def _read_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as data_file:
            value = json.load(data_file)
    except (OSError, json.JSONDecodeError) as error:
        raise CountryDataError(f"Could not read valid country data from {path}: {error}") from error
    if not isinstance(value, dict):
        raise CountryDataError(f"Country data root must be an object: {path}")
    return value


def _valid_position(value: object, *, minimum_longitude: float = -180, maximum_longitude: float = 180) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(coordinate, (int, float)) and not isinstance(coordinate, bool) for coordinate in value)
        and minimum_longitude <= value[0] <= maximum_longitude
        and -90 <= value[1] <= 90
    )


def load_country_data(
    metadata_path: Path | None = None, geometry_path: Path | None = None
) -> tuple[dict, dict]:
    metadata_path = metadata_path or settings.BASE_DIR / "data" / "countries.json"
    geometry_path = geometry_path or settings.BASE_DIR / "static" / "data" / "countries.geojson"
    metadata = _read_json(metadata_path)
    geometry = _read_json(geometry_path)
    validate_country_data(metadata, geometry)
    return metadata, geometry


def validate_country_data(metadata: dict, geometry: dict) -> None:
    if metadata.get("schema_version") != 1 or not isinstance(metadata.get("source"), dict):
        raise CountryDataError("Country metadata has an unsupported or missing schema")
    countries = metadata.get("countries")
    if not isinstance(countries, list) or len(countries) != EXPECTED_COUNTRY_COUNT:
        raise CountryDataError(f"Country metadata must contain {EXPECTED_COUNTRY_COUNT} countries")

    metadata_codes = []
    for index, country in enumerate(countries):
        if not isinstance(country, dict) or set(country) != COUNTRY_FIELDS:
            raise CountryDataError(f"Country metadata item {index} has invalid fields")
        alpha_2 = country["iso_a2"]
        alpha_3 = country["iso_a3"]
        if not isinstance(alpha_2, str) or not ALPHA_2_PATTERN.fullmatch(alpha_2):
            raise CountryDataError(f"Country metadata item {index} has invalid ISO alpha-2")
        if not isinstance(alpha_3, str) or not ALPHA_3_PATTERN.fullmatch(alpha_3):
            raise CountryDataError(f"Country {alpha_2} has invalid ISO alpha-3")
        if not all(isinstance(country[field], str) and country[field] for field in ("name", "region", "subregion", "flag")):
            raise CountryDataError(f"Country {alpha_2} has invalid identity text")
        if not _valid_position(country["centroid"]):
            raise CountryDataError(f"Country {alpha_2} has an invalid centroid")
        bounds = country["bounds"]
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not _valid_position(bounds[0])
            or not _valid_position(bounds[1], maximum_longitude=540)
            or bounds[1][0] < bounds[0][0]
            or bounds[1][0] - bounds[0][0] > 360
            or bounds[1][1] < bounds[0][1]
        ):
            raise CountryDataError(f"Country {alpha_2} has invalid bounds")
        if not isinstance(country["small"], bool):
            raise CountryDataError(f"Country {alpha_2} has an invalid small-country marker")
        metadata_codes.append(alpha_2)

    if len(metadata_codes) != len(set(metadata_codes)):
        raise CountryDataError("Country metadata ISO alpha-2 codes must be unique")
    if not {"VA", "MC", "NR"}.issubset(
        {country["iso_a2"] for country in countries if country["small"]}
    ):
        raise CountryDataError("Expected microstate hit-target metadata is missing")

    if geometry.get("type") != "FeatureCollection" or not isinstance(geometry.get("features"), list):
        raise CountryDataError("Country geometry must be a GeoJSON FeatureCollection")
    geometry_codes = []
    for index, feature in enumerate(geometry["features"]):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        feature_geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if (
            feature.get("type") != "Feature"
            or not isinstance(properties, dict)
            or not isinstance(feature_geometry, dict)
            or feature_geometry.get("type") != "MultiPolygon"
            or not feature_geometry.get("coordinates")
        ):
            raise CountryDataError(f"Country geometry feature {index} is invalid")
        alpha_2 = properties.get("iso_a2")
        if feature.get("id") != alpha_2 or not isinstance(alpha_2, str) or not ALPHA_2_PATTERN.fullmatch(alpha_2):
            raise CountryDataError(f"Country geometry feature {index} has an invalid identity")
        geometry_codes.append(alpha_2)

    if len(geometry_codes) != len(set(geometry_codes)):
        raise CountryDataError("Country geometry ISO alpha-2 codes must be unique")
    if set(metadata_codes) != set(geometry_codes):
        raise CountryDataError("Country geometry and metadata ISO alpha-2 codes do not match")