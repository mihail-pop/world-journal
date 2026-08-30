from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings


EXPECTED_COUNTRY_COUNT = 238
EXPECTED_CAPITAL_COUNT = 198
EXPECTED_CAPITAL_COUNTRY_COUNT = 194
EXPECTED_MULTIPLE_CAPITALS = {"BO": 2, "CI": 2, "ZA": 3}
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
CAPITAL_ID_PATTERN = re.compile(r"^ne-\d+$")


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


def load_capital_data(
    country_metadata: dict | None = None, capital_path: Path | None = None
) -> dict:
    if country_metadata is None:
        country_metadata, _geometry = load_country_data()
    capital_path = capital_path or settings.BASE_DIR / "static" / "data" / "capitals.geojson"
    capital_data = _read_json(capital_path)
    validate_capital_data(
        capital_data, {country["iso_a2"] for country in country_metadata["countries"]}
    )
    return capital_data


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


def validate_capital_data(capital_data: dict, country_codes: set[str]) -> None:
    if (
        set(capital_data) != {"type", "schema_version", "source", "features"}
        or capital_data.get("type") != "FeatureCollection"
        or capital_data.get("schema_version") != 1
        or not isinstance(capital_data.get("source"), dict)
        or capital_data["source"].get("name") != "ne_10m_populated_places"
        or capital_data["source"].get("dataset_version") != "5.1.2"
    ):
        raise CountryDataError("Capital data has an unsupported or missing schema")
    features = capital_data.get("features")
    if not isinstance(features, list) or len(features) != EXPECTED_CAPITAL_COUNT:
        raise CountryDataError(f"Capital data must contain {EXPECTED_CAPITAL_COUNT} features")

    feature_ids = []
    capital_counts: dict[str, int] = {}
    for index, feature in enumerate(features):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        feature_id = feature.get("id") if isinstance(feature, dict) else None
        if (
            set(feature) != {"type", "id", "properties", "geometry"}
            or feature.get("type") != "Feature"
            or not isinstance(feature_id, str)
            or not CAPITAL_ID_PATTERN.fullmatch(feature_id)
            or not isinstance(properties, dict)
            or set(properties) != {"name", "iso_a2"}
            or not isinstance(geometry, dict)
            or set(geometry) != {"type", "coordinates"}
            or geometry.get("type") != "Point"
            or not _valid_position(geometry.get("coordinates"))
        ):
            raise CountryDataError(f"Capital feature {index} is invalid")
        name = properties["name"]
        alpha_2 = properties["iso_a2"]
        if not isinstance(name, str) or not name or "\ufffd" in name:
            raise CountryDataError(f"Capital feature {feature_id} has an invalid name")
        if alpha_2 not in country_codes:
            raise CountryDataError(f"Capital feature {feature_id} has no canonical country join")
        feature_ids.append(feature_id)
        capital_counts[alpha_2] = capital_counts.get(alpha_2, 0) + 1

    if len(feature_ids) != len(set(feature_ids)):
        raise CountryDataError("Capital feature identifiers must be unique")
    if len(capital_counts) != EXPECTED_CAPITAL_COUNTRY_COUNT:
        raise CountryDataError(
            f"Capital data must join {EXPECTED_CAPITAL_COUNTRY_COUNT} countries"
        )
    multiple_capitals = {
        code: count for code, count in capital_counts.items() if count > 1
    }
    if multiple_capitals != EXPECTED_MULTIPLE_CAPITALS:
        raise CountryDataError("Capital data has unexpected multiple-capital records")