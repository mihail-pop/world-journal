"""Prebuild unchanged Adventure country hues from bundled geometry.

Uses only the Python standard library, with no network or app dependency.
Country geometry is read-only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static/data/countries.geojson"
OUTPUT = ROOT / "static/data/adventure-map.json"


def country_colors(features):
    # Same edge ownership, ordering and FNV-1a preference as the original JS.
    edges, neighbors = {}, {}
    for feature in features:
        code = feature["properties"]["iso_a2"]
        neighbors[code] = set()
        geometry = feature["geometry"]
        parts = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for part in parts:
            for ring in part:
                for a, b in zip(ring, ring[1:]):
                    edge = tuple(sorted((tuple(a), tuple(b))))
                    edges.setdefault(edge, set()).add(code)
    for owners in edges.values():
        for code in owners:
            neighbors[code].update(owners - {code})
    colors = {}
    for code in sorted(neighbors, key=lambda value: (-len(neighbors[value]), value)):
        value = 2166136261
        for char in code:
            value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
        preferred = value % 8
        used = {colors.get(other) for other in neighbors[code]}
        colors[code] = next((index for offset in range(8) if (index := (preferred + offset) % 8) not in used), preferred)
    return colors


def build():
    content = SOURCE.read_bytes()
    features = json.loads(content)["features"]
    data = {"version": 1, "geometry_sha256": hashlib.sha256(content).hexdigest(),
            "colors": country_colors(features)}
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Built {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
