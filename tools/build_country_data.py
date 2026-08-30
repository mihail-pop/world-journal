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
SIMPLIFY_TOLERANCE = 0.015
COORDINATE_PRECISION = 4
USER_AGENT = "world-journal-country-data-builder/1.0"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = PROJECT_ROOT / "data" / "countries.json"
GEOMETRY_PATH = PROJECT_ROOT / "static" / "data" / "countries.geojson"


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


def squared_segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    x, y = start
    delta_x = end[0] - x
    delta_y = end[1] - y
    if delta_x or delta_y:
        projection = ((point[0] - x) * delta_x + (point[1] - y) * delta_y) / (
            delta_x * delta_x + delta_y * delta_y
        )
        if projection > 1:
            x, y = end
        elif projection > 0:
            x += delta_x * projection
            y += delta_y * projection
    return (point[0] - x) ** 2 + (point[1] - y) ** 2


def simplify_open_line(
    points: list[tuple[float, float]], tolerance_squared: float
) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    greatest_distance = 0.0
    split_index = 0
    for index, point in enumerate(points[1:-1], start=1):
        distance = squared_segment_distance(point, points[0], points[-1])
        if distance > greatest_distance:
            split_index = index
            greatest_distance = distance
    if greatest_distance <= tolerance_squared:
        return [points[0], points[-1]]
    left = simplify_open_line(points[: split_index + 1], tolerance_squared)
    right = simplify_open_line(points[split_index:], tolerance_squared)
    return left[:-1] + right


def simplify_ring(ring: list[tuple[float, float]]) -> list[list[float]]:
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 4:
        simplified = ring
    else:
        anchor = ring[0]
        split_index = max(
            range(1, len(ring)),
            key=lambda index: (ring[index][0] - anchor[0]) ** 2
            + (ring[index][1] - anchor[1]) ** 2,
        )
        tolerance_squared = SIMPLIFY_TOLERANCE**2
        first = simplify_open_line(ring[: split_index + 1], tolerance_squared)
        second = simplify_open_line(
            ring[split_index:] + [ring[0]], tolerance_squared
        )
        simplified = first[:-1] + second[:-1]
        if len(simplified) < 3:
            simplified = ring
    rounded = [
        [round(longitude, COORDINATE_PRECISION), round(latitude, COORDINATE_PRECISION)]
        for longitude, latitude in simplified
    ]
    rounded.append(rounded[0])
    return rounded


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
    prepared = [(signed_area(ring), simplify_ring(ring)) for ring in rings if len(ring) >= 4]
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
    write_json(METADATA_PATH, metadata, compact=False)
    write_json(GEOMETRY_PATH, geometry, compact=True)
    print(f"Wrote {len(metadata['countries'])} countries")
    print(f"Metadata: {METADATA_PATH} ({METADATA_PATH.stat().st_size:,} bytes)")
    print(f"Geometry: {GEOMETRY_PATH} ({GEOMETRY_PATH.stat().st_size:,} bytes)")
    print(f"Excluded source records: {len(exclusions)}")
    for exclusion in exclusions:
        print(f"- {exclusion['name']} ({exclusion['adm0_a3']}): {exclusion['reason']}")


if __name__ == "__main__":
    main()