"""Build browser country geometry and metadata from pinned Natural Earth data."""

from __future__ import annotations

import hashlib
import json
import struct
import urllib.request
from collections import defaultdict
from pathlib import Path


SOURCE_TAG = "v5.1.2"
DATASET_VERSION = "5.1.1"
SOURCE_NAME = "ne_10m_admin_0_countries"
SOURCE_BASE_URL = (
    f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{SOURCE_TAG}/10m_cultural/{SOURCE_NAME}"
)
SOURCE_EXTENSIONS = (".dbf", ".shp", ".VERSION.txt")
EXPECTED_SOURCE_SHA256 = {
    ".dbf": "c5dbd3dd5fd7e2ef49051fc88562c03819e8ea63a382642df6eadd1243bf4b49",
    ".shp": "7ce119ef6342e43cff7c0c3004e0911ab7ec1988a14734372031d2012180e7bc",
    ".VERSION.txt": "f9893302cd3158f3b5aea394dcd2a91574869e9e6ff69e9235b10a3bf8c983fb",
}
EXPECTED_SOURCE_RECORDS = 258
EXPECTED_COUNTRIES = 238
CAPITAL_SOURCE_NAME = "ne_10m_populated_places"
CAPITAL_SOURCE_BASE_URL = (
    f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{SOURCE_TAG}/10m_cultural/{CAPITAL_SOURCE_NAME}"
)
CAPITAL_DATASET_VERSION = "5.1.2"
CAPITAL_SOURCE_EXTENSIONS = (".dbf", ".VERSION.txt")
EXPECTED_CAPITAL_SOURCE_SHA256 = {
    ".dbf": "eff834a8727e06f28fc52b04393c462d074aecf9a7acd1b870e766240a995b6c",
    ".VERSION.txt": "0c9a9d43610d66f4cc3f42da08cae044483de25894a9daf9dc6a76ff75ca9327",
}
EXPECTED_CAPITAL_SOURCE_RECORDS = 7342
EXPECTED_CAPITALS = 198
EXPECTED_CAPITAL_COUNTRIES = 194
EXPECTED_MULTIPLE_CAPITALS = {"BO": 2, "CI": 2, "ZA": 3}
EXPECTED_CAPITAL_EXCLUSIONS = {"1159149757", "1159151189"}
# Coverage simplification uses triangle area, not the old per-ring distance
# tolerance. This value keeps the browser asset near its prior point budget.
SIMPLIFY_TOLERANCE = 0.03
COORDINATE_PRECISION = 4
USER_AGENT = "world-journal-country-data-builder/1.0"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = PROJECT_ROOT / "data" / "countries.json"
GEOMETRY_PATH = PROJECT_ROOT / "static" / "data" / "countries.geojson"
CAPITALS_PATH = PROJECT_ROOT / "static" / "data" / "capitals.geojson"


def download_source() -> tuple[dict[str, bytes], dict[str, str]]:
    source_files = {}
    source_hashes = {}
    for extension in SOURCE_EXTENSIONS:
        request = urllib.request.Request(
            f"{SOURCE_BASE_URL}{extension}", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        source_files[extension] = content
        source_hashes[extension] = hashlib.sha256(content).hexdigest()
        if source_hashes[extension] != EXPECTED_SOURCE_SHA256[extension]:
            raise ValueError(f"Source hash mismatch for {extension}")
    return source_files, source_hashes


def download_capital_source() -> tuple[dict[str, bytes], dict[str, str]]:
    source_files = {}
    source_hashes = {}
    for extension in CAPITAL_SOURCE_EXTENSIONS:
        request = urllib.request.Request(
            f"{CAPITAL_SOURCE_BASE_URL}{extension}", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        source_files[extension] = content
        source_hashes[extension] = hashlib.sha256(content).hexdigest()
        if source_hashes[extension] != EXPECTED_CAPITAL_SOURCE_SHA256[extension]:
            raise ValueError(f"Capital source hash mismatch for {extension}")
    return source_files, source_hashes


def parse_dbf(content: bytes) -> list[dict[str, str]]:
    record_count = struct.unpack("<I", content[4:8])[0]
    header_length = struct.unpack("<H", content[8:10])[0]
    record_length = struct.unpack("<H", content[10:12])[0]
    fields = []
    position = 32

    while content[position] != 0x0D:
        descriptor = content[position : position + 32]
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, descriptor[16]))
        position += 32

    records = []
    for index in range(record_count):
        start = header_length + index * record_length
        record = content[start : start + record_length]
        if record[:1] == b"*":
            continue
        row = {}
        offset = 1
        for name, length in fields:
            row[name] = record[offset : offset + length].decode(
                "utf-8", errors="replace"
            ).strip(" \x00")
            offset += length
        records.append(row)
    return records


def parse_shapefile(content: bytes) -> list[list[list[tuple[float, float]]]]:
    if struct.unpack(">I", content[:4])[0] != 9994:
        raise ValueError("Unexpected shapefile magic number")
    if struct.unpack("<I", content[32:36])[0] != 5:
        raise ValueError("Expected Polygon shapefile geometry")

    shapes = []
    position = 100
    while position < len(content):
        content_length = struct.unpack(">I", content[position + 4 : position + 8])[0] * 2
        record = content[position + 8 : position + 8 + content_length]
        shape_type = struct.unpack("<I", record[:4])[0]
        if shape_type == 0:
            shapes.append([])
        elif shape_type == 5:
            part_count, point_count = struct.unpack("<II", record[36:44])
            part_offset = 44
            point_offset = part_offset + part_count * 4
            starts = list(
                struct.unpack(
                    f"<{part_count}I", record[part_offset : part_offset + part_count * 4]
                )
            )
            starts.append(point_count)
            points = [
                struct.unpack("<dd", record[point_offset + index * 16 : point_offset + (index + 1) * 16])
                for index in range(point_count)
            ]
            shapes.append([points[starts[index] : starts[index + 1]] for index in range(part_count)])
        else:
            raise ValueError(f"Unsupported shapefile geometry type: {shape_type}")
        position += 8 + content_length
    return shapes


def signed_area(ring: list[tuple[float, float]]) -> float:
    return sum(
        first_x * second_y - second_x * first_y
        for (first_x, first_y), (second_x, second_y) in zip(ring, ring[1:])
    ) / 2


def point_in_ring(point: list[float], ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing = (previous[0] - current[0]) * (point[1] - current[1]) / (
                previous[1] - current[1]
            ) + current[0]
            if point[0] < crossing:
                inside = not inside
        previous = current
    return inside


def rings_to_polygons(
    rings: list[list[tuple[float, float]]],
) -> list[list[list[list[float]]]]:
    # Keep the source geometry intact here. Simplification happens once across
    # the entire coverage, so both sides of every shared border stay identical.
    prepared = [(signed_area(ring), [[x, y] for x, y in ring]) for ring in rings if len(ring) >= 4]
    outer_rings = [ring for area, ring in prepared if area < 0]
    holes = [ring for area, ring in prepared if area >= 0]
    if not outer_rings:
        raise ValueError("Shape contains no outer polygon ring")
    polygons = [[outer] for outer in outer_rings]
    for hole in holes:
        containers = [
            (abs(signed_area([(point[0], point[1]) for point in outer])), index)
            for index, outer in enumerate(outer_rings)
            if point_in_ring(hole[0], outer)
        ]
        if not containers:
            raise ValueError("Polygon hole is not contained by an outer ring")
        _, container_index = min(containers)
        polygons[container_index].append(hole)
    return polygons


def simplify_country_coverage(geometry: dict) -> None:
    try:
        import shapely
        from shapely.geometry import mapping, shape
    except ImportError as error:
        raise RuntimeError(
            "Country regeneration requires optional maintainer dependencies: "
            ".venv/Scripts/python.exe -m pip install -r tools/requirements-country-data.txt"
        ) from error

    if shapely.geos_version < (3, 12, 0):
        raise RuntimeError("Country coverage simplification requires GEOS 3.12 or newer")
    features = geometry["features"]
    coverage = []
    repaired = []
    for feature in features:
        country = shape(feature["geometry"])
        if not country.is_valid:
            # Natural Earth's source has a self-crossing ring in Egypt and
            # touching/overlapping same-country parts in merged BR/KZ records.
            # Repair polygon structure before building the shared coverage.
            country = shapely.make_valid(country, method="structure", keep_collapsed=False)
            repaired.append(feature["id"])
        country = shapely.set_precision(country, grid_size=1e-8)
        if country.is_empty or country.geom_type not in {"Polygon", "MultiPolygon"} or not country.is_valid:
            raise ValueError(f"Source country {feature['id']} cannot form a valid polygon")
        coverage.append(country)
    if repaired:
        print(f"Repaired source polygon structure: {', '.join(repaired)}")
    if not shapely.coverage_is_valid(coverage):
        edges = shapely.coverage_invalid_edges(coverage)
        invalid = [feature["id"] for feature, edge in zip(features, edges) if not edge.is_empty]
        raise ValueError(f"Source boundaries are not edge-matched: {', '.join(invalid)}")

    simplified = shapely.coverage_simplify(coverage, tolerance=SIMPLIFY_TOLERANCE)
    # Round the whole coverage on the same grid, not individual country rings.
    # Valid-output precision retains usable rings and removes collapsed pieces.
    rounded = shapely.set_precision(simplified, grid_size=10 ** -COORDINATE_PRECISION)
    if not all(shapely.is_valid(rounded)) or not shapely.coverage_is_valid(rounded):
        raise ValueError("Simplified country boundaries do not form a valid coverage")
    for feature, original, result in zip(features, coverage, rounded):
        if result.is_empty:
            raise ValueError(f"Simplification removed country {feature['id']}")
        if shapely.get_num_geometries(result) != shapely.get_num_geometries(original):
            raise ValueError(f"Simplification removed an island of {feature['id']}")
        if result.geom_type == "Polygon":
            result = shapely.MultiPolygon([result])
        mapped = mapping(result)
        # GEOS's precision grid still uses binary floats. Avoid exporting long
        # tails such as 12.300000000000002; equal shared coordinates round alike.
        mapped["coordinates"] = [
            [[[round(x, COORDINATE_PRECISION), round(y, COORDINATE_PRECISION)] for x, y in ring]
             for ring in polygon]
            for polygon in mapped["coordinates"]
        ]
        feature["geometry"] = mapped
    exported = [shape(feature["geometry"]) for feature in features]
    if not all(shapely.is_valid(exported)) or not shapely.coverage_is_valid(exported):
        raise ValueError("Rounded GeoJSON would introduce invalid country boundaries")
    print(f"Country coordinate points: {int(shapely.get_num_coordinates(exported).sum()):,}")


def is_iso_backed(record: dict[str, str]) -> bool:
    alpha_2 = record["ISO_A2_EH"]
    alpha_3 = record["ISO_A3_EH"]
    numeric = record["ISO_N3_EH"]
    return (
        len(alpha_2) == 2
        and alpha_2.isascii()
        and alpha_2.isalpha()
        and alpha_2.isupper()
        and len(alpha_3) == 3
        and alpha_3.isascii()
        and alpha_3.isalpha()
        and alpha_3.isupper()
        and len(numeric) == 3
        and numeric.isdigit()
    )


def flag_for(alpha_2: str) -> str:
    return "".join(chr(0x1F1E6 + ord(character) - ord("A")) for character in alpha_2)


def circular_longitude_bounds(longitudes: list[float]) -> tuple[float, float]:
    normalized = sorted(longitude % 360 for longitude in longitudes)
    gaps = [
        ((normalized[(index + 1) % len(normalized)] - normalized[index]) % 360, index)
        for index in range(len(normalized))
    ]
    _, gap_index = max(gaps)
    west = normalized[(gap_index + 1) % len(normalized)]
    span = (normalized[gap_index] - west) % 360
    if west > 180:
        west -= 360
    return west, west + span


def choose_metadata_record(records: list[dict[str, str]]) -> dict[str, str]:
    return min(
        records,
        key=lambda record: (
            record["ADM0_A3"] != record["ISO_A3_EH"],
            record["TYPE"] not in {"Sovereign country", "Country", "Sovereignty"},
            record["ADMIN"],
        ),
    )


def build_outputs(
    records: list[dict[str, str]], shapes: list[list[list[tuple[float, float]]]]
) -> tuple[dict, dict, list[dict[str, str]]]:
    if len(records) != EXPECTED_SOURCE_RECORDS or len(shapes) != EXPECTED_SOURCE_RECORDS:
        raise ValueError(
            f"Expected {EXPECTED_SOURCE_RECORDS} aligned records, got "
            f"{len(records)} metadata and {len(shapes)} shapes"
        )

    grouped_records = defaultdict(list)
    grouped_polygons = defaultdict(list)
    grouped_points = defaultdict(list)
    exclusions = []
    for record, rings in zip(records, shapes):
        if not is_iso_backed(record):
            exclusions.append(
                {
                    "name": record["ADMIN"],
                    "type": record["TYPE"],
                    "adm0_a3": record["ADM0_A3"],
                    "iso_a2_eh": record["ISO_A2_EH"],
                    "reason": "No complete ISO 3166 alpha-2, alpha-3, and numeric identity",
                }
            )
            continue
        alpha_2 = record["ISO_A2_EH"]
        grouped_records[alpha_2].append(record)
        grouped_polygons[alpha_2].extend(rings_to_polygons(rings))
        grouped_points[alpha_2].extend(point for ring in rings for point in ring)

    if len(grouped_records) != EXPECTED_COUNTRIES:
        raise ValueError(
            f"Expected {EXPECTED_COUNTRIES} unique ISO countries, got {len(grouped_records)}"
        )

    countries = []
    features = []
    for alpha_2 in sorted(grouped_records):
        record = choose_metadata_record(grouped_records[alpha_2])
        points = grouped_points[alpha_2]
        west, east = circular_longitude_bounds([point[0] for point in points])
        south = min(point[1] for point in points)
        north = max(point[1] for point in points)
        small = record["TINY"] != "-99"
        country = {
            "iso_a2": alpha_2,
            "iso_a3": record["ISO_A3_EH"],
            "name": record["NAME_EN"],
            "region": record["REGION_UN"],
            "subregion": record["SUBREGION"],
            "centroid": [float(record["LABEL_X"]), float(record["LABEL_Y"])],
            "bounds": [
                [round(west, COORDINATE_PRECISION), round(south, COORDINATE_PRECISION)],
                [round(east, COORDINATE_PRECISION), round(north, COORDINATE_PRECISION)],
            ],
            "flag": flag_for(alpha_2),
            "small": small,
        }
        countries.append(country)
        features.append(
            {
                "type": "Feature",
                "id": alpha_2,
                "properties": {
                    "iso_a2": alpha_2,
                    "name": country["name"],
                    "small": small,
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": grouped_polygons[alpha_2],
                },
            }
        )

    metadata = {
        "schema_version": 1,
        "source": {
            "name": SOURCE_NAME,
            "dataset_version": DATASET_VERSION,
            "repository_tag": SOURCE_TAG,
            "resolution": "1:10m",
            "license": "Public domain",
            "boundary_policy": "Natural Earth de facto boundaries",
        },
        "countries": countries,
    }
    geometry = {"type": "FeatureCollection", "features": features}
    simplify_country_coverage(geometry)
    return metadata, geometry, exclusions


def validate_outputs(metadata: dict, geometry: dict) -> None:
    countries = metadata["countries"]
    metadata_codes = [country["iso_a2"] for country in countries]
    geometry_codes = [feature["properties"]["iso_a2"] for feature in geometry["features"]]
    if len(metadata_codes) != EXPECTED_COUNTRIES:
        raise ValueError(f"Expected {EXPECTED_COUNTRIES} metadata countries")
    if len(metadata_codes) != len(set(metadata_codes)):
        raise ValueError("Country metadata contains duplicate ISO alpha-2 codes")
    if set(metadata_codes) != set(geometry_codes):
        raise ValueError("Geometry and metadata ISO alpha-2 sets do not match")
    if any(len(code) != 2 or not code.isalpha() or not code.isupper() for code in metadata_codes):
        raise ValueError("Country metadata contains an invalid ISO alpha-2 code")
    if any(not feature["geometry"]["coordinates"] for feature in geometry["features"]):
        raise ValueError("A selectable country has no geometry")
    if not any(country["iso_a2"] == "VA" and country["small"] for country in countries):
        raise ValueError("Vatican microstate hit-target metadata is missing")


def build_capital_output(
    records: list[dict[str, str]], country_codes: set[str], source_hashes: dict[str, str]
) -> tuple[dict, list[dict[str, str]]]:
    if len(records) != EXPECTED_CAPITAL_SOURCE_RECORDS:
        raise ValueError(
            f"Expected {EXPECTED_CAPITAL_SOURCE_RECORDS} populated-place records, got {len(records)}"
        )

    features = []
    exclusions = []
    for record in records:
        if record["ADM0CAP"] != "1":
            continue
        if record["ISO_A2"] not in country_codes:
            exclusions.append(record)
            continue
        name = record["NAME_EN"] or record["NAMEASCII"]
        feature_id = record["NE_ID"]
        if not feature_id.isdigit() or not name or "\ufffd" in name:
            raise ValueError(f"Capital record {feature_id or '<missing>'} has invalid identity")
        longitude = float(record["LONGITUDE"])
        latitude = float(record["LATITUDE"])
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError(f"Capital record {feature_id} has invalid coordinates")
        features.append(
            {
                "type": "Feature",
                "id": f"ne-{feature_id}",
                "properties": {"name": name, "iso_a2": record["ISO_A2"]},
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        round(longitude, COORDINATE_PRECISION),
                        round(latitude, COORDINATE_PRECISION),
                    ],
                },
            }
        )

    features.sort(key=lambda feature: (feature["properties"]["iso_a2"], feature["properties"]["name"], feature["id"]))
    capital_data = {
        "type": "FeatureCollection",
        "schema_version": 1,
        "source": {
            "name": CAPITAL_SOURCE_NAME,
            "dataset_version": CAPITAL_DATASET_VERSION,
            "repository_tag": SOURCE_TAG,
            "resolution": "1:10m",
            "license": "Public domain",
            "inclusion": "ADM0CAP=1 with an exact canonical ISO_A2 join",
            "sha256": source_hashes,
        },
        "features": features,
    }
    validate_capital_output(capital_data, exclusions)
    return capital_data, exclusions


def validate_capital_output(capital_data: dict, exclusions: list[dict[str, str]]) -> None:
    features = capital_data["features"]
    feature_ids = [feature["id"] for feature in features]
    country_counts: dict[str, int] = defaultdict(int)
    for feature in features:
        country_counts[feature["properties"]["iso_a2"]] += 1
    multiple_capitals = {
        code: count for code, count in country_counts.items() if count > 1
    }

    if len(features) != EXPECTED_CAPITALS:
        raise ValueError(f"Expected {EXPECTED_CAPITALS} joined capitals, got {len(features)}")
    if len(country_counts) != EXPECTED_CAPITAL_COUNTRIES:
        raise ValueError(
            f"Expected capitals for {EXPECTED_CAPITAL_COUNTRIES} countries, got {len(country_counts)}"
        )
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("Capital feature identifiers must be unique")
    if multiple_capitals != EXPECTED_MULTIPLE_CAPITALS:
        raise ValueError(f"Unexpected multiple-capital records: {multiple_capitals}")
    if {record["NE_ID"] for record in exclusions} != EXPECTED_CAPITAL_EXCLUSIONS:
        raise ValueError("Unexpected national-capital ISO exclusions")


def write_json(path: Path, value: dict, *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(
            value,
            output,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
            sort_keys=False,
        )
        output.write("\n")


def main() -> None:
    source_files, source_hashes = download_source()
    version = source_files[".VERSION.txt"].decode("ascii").strip()
    if version != DATASET_VERSION:
        raise ValueError(f"Expected dataset version {DATASET_VERSION}, got {version}")
    records = parse_dbf(source_files[".dbf"])
    shapes = parse_shapefile(source_files[".shp"])
    metadata, geometry, exclusions = build_outputs(records, shapes)
    metadata["source"]["sha256"] = source_hashes
    validate_outputs(metadata, geometry)
    capital_source_files, capital_source_hashes = download_capital_source()
    capital_version = capital_source_files[".VERSION.txt"].decode("ascii").strip()
    if capital_version != CAPITAL_DATASET_VERSION:
        raise ValueError(
            f"Expected capital dataset version {CAPITAL_DATASET_VERSION}, got {capital_version}"
        )
    capital_records = parse_dbf(capital_source_files[".dbf"])
    capital_data, capital_exclusions = build_capital_output(
        capital_records,
        {country["iso_a2"] for country in metadata["countries"]},
        capital_source_hashes,
    )
    write_json(METADATA_PATH, metadata, compact=False)
    write_json(GEOMETRY_PATH, geometry, compact=True)
    write_json(CAPITALS_PATH, capital_data, compact=True)
    print(f"Wrote {len(metadata['countries'])} countries")
    print(f"Metadata: {METADATA_PATH} ({METADATA_PATH.stat().st_size:,} bytes)")
    print(f"Geometry: {GEOMETRY_PATH} ({GEOMETRY_PATH.stat().st_size:,} bytes)")
    print(f"Excluded source records: {len(exclusions)}")
    for exclusion in exclusions:
        print(f"- {exclusion['name']} ({exclusion['adm0_a3']}): {exclusion['reason']}")
    print(f"Capitals: {CAPITALS_PATH} ({CAPITALS_PATH.stat().st_size:,} bytes)")
    print(f"National capitals: {len(capital_data['features'])}")
    print(f"Excluded national-capital records: {len(capital_exclusions)}")
    for exclusion in capital_exclusions:
        print(
            f"- {exclusion['NAME']} ({exclusion['ADM0_A3']}): "
            "No exact canonical ISO alpha-2 join"
        )


if __name__ == "__main__":
    main()
