"""Build the offline place-search index from the map's pinned populated-place source."""
import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

from build_country_data import (
    CAPITAL_DATASET_VERSION, CAPITAL_SOURCE_BASE_URL, CAPITAL_SOURCE_NAME,
    EXPECTED_CAPITAL_SOURCE_RECORDS, EXPECTED_CAPITAL_SOURCE_SHA256,
    PROJECT_ROOT, SOURCE_TAG, USER_AGENT, parse_dbf,
)


def build(source):
    digest = hashlib.sha256(source).hexdigest()
    if digest != EXPECTED_CAPITAL_SOURCE_SHA256[".dbf"]:
        raise ValueError("Populated-place source hash mismatch")
    records = parse_dbf(source)
    if len(records) != EXPECTED_CAPITAL_SOURCE_RECORDS:
        raise ValueError("Unexpected populated-place record count")
    countries = json.loads((PROJECT_ROOT / "data/countries.json").read_text(encoding="utf-8"))["countries"]
    codes = {row["iso_a2"] for row in countries}
    alpha3 = {row["iso_a3"]: row["iso_a2"] for row in countries if row["iso_a3"]}
    alpha3.update({"KOS": "XK", "CYN": "XC", "SOL": "XL", "SJM": "NO"})
    places = []
    for row in records:
        code = row["ISO_A2"] if row["ISO_A2"] in codes else alpha3.get(row["ADM0_A3"])
        if code not in codes:
            raise ValueError(f"Cannot join place {row['NE_ID']} to a map country")
        name = row["NAME_EN"] or row["NAMEASCII"] or row["NAME"]
        aliases = {value for key, value in row.items() if key.startswith("NAME_") and value}
        aliases.update(filter(None, re.split(r"[|;]", row["NAMEALT"])))
        aliases.update([row["NAME"], row["NAMEASCII"]])
        if code == "RO" and name == "Bucharest":
            aliases.add("București")
        aliases.discard(name)
        aliases.discard("")
        coordinates = [round(float(row["LONGITUDE"]), 5), round(float(row["LATITUDE"]), 5)]
        if not row["NE_ID"].isdigit() or not name or not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90:
            raise ValueError(f"Invalid place {row['NE_ID']}")
        places.append({
            "id": f"ne-{row['NE_ID']}", "name": name, "country": code,
            "kind": "capital" if row["ADM0CAP"] == "1" else "city",
            "region": row["ADM1NAME"], "coordinates": coordinates,
            "population": int(row["POP_MAX"]), "aliases": sorted(aliases),
        })
    places.sort(key=lambda place: (place["country"], place["name"], place["id"]))
    if len({place["id"] for place in places}) != len(places):
        raise ValueError("Duplicate place identities")
    metadata = {
        "schema_version": 1,
        "source": {
            "name": CAPITAL_SOURCE_NAME, "dataset_version": CAPITAL_DATASET_VERSION,
            "repository_tag": SOURCE_TAG, "license": "Public domain", "sha256": digest,
            "coverage": "Major cities, capitals and a selection of smaller towns; not every settlement.",
        },
    }
    output = PROJECT_ROOT / "data/place_search.json"
    header = json.dumps(metadata, ensure_ascii=False, indent=2).rstrip()[:-1]
    rows = ",\n".join("    " + json.dumps(place, ensure_ascii=False, separators=(",", ":")) for place in places)
    output.write_text(header.rstrip() + ',\n  "places": [\n' + rows + "\n  ]\n}\n", encoding="utf-8")
    print(f"Built {len(places):,} searchable places in {output.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Use a previously downloaded, hash-verified source DBF")
    args = parser.parse_args()
    if args.source:
        source = args.source.read_bytes()
    else:
        request = urllib.request.Request(CAPITAL_SOURCE_BASE_URL + ".dbf", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            source = response.read()
    build(source)
