# Country data provenance

World Journal bundles application-owned country geometry and metadata so country selection does not depend on a map-style provider.

## Source

- Dataset: Natural Earth `ne_10m_admin_0_countries`
- Resolution: 1:10m
- Dataset version: 5.1.1
- Immutable repository tag: `nvkelso/natural-earth-vector` v5.1.2
- License: public domain
- Boundary policy: Natural Earth's default de facto boundaries show control on the ground and do not adjudicate sovereignty.

Source files and expected SHA-256 hashes are pinned in `tools/build_country_data.py`. The generated metadata also records those hashes.

## Reproduction

Run:

```powershell
.\.venv\Scripts\python.exe tools\build_country_data.py
```

The script uses only the Python standard library. It downloads the tagged SHP, DBF, and version files; verifies their hashes; parses the aligned 258 source records; simplifies polygon rings with a 0.015-degree tolerance; rounds coordinates to four decimal places; and writes:

- `data/countries.json`
- `static/data/countries.geojson`

Generation fails unless it produces exactly 238 unique ISO-backed metadata and geometry records with an exact join.

## ISO policy and exceptions

A source record is selectable only when Natural Earth's `ISO_A2_EH`, `ISO_A3_EH`, and `ISO_N3_EH` fields form a complete ISO 3166 identity. Duplicate records for France/Clipperton Island, Kazakhstan/Baykonur, Brazil/Brazilian Island, and Australia/its grouped dependencies are merged into one MultiPolygon per ISO alpha-2 code.

The following source records are not assigned invented ISO codes and are not selectable: Dhekelia Sovereign Base Area, Somaliland, Kosovo (`XK` is user-assigned, not ISO 3166), US Naval Base Guantanamo Bay, Northern Cyprus, Cyprus No Mans Area, Siachen Glacier, Akrotiri Sovereign Base Area, Southern Patagonian Ice Field, Bir Tawil, Spratly Islands, Bajo Nuevo Bank, Serranilla Bank, and Scarborough Reef.

Natural Earth's Admin 0 countries theme groups some dependencies with administering countries. The application preserves that source policy instead of synthesizing separate boundaries from unrelated data.

## Small-country interaction

Records carrying Natural Earth's `TINY` classification are marked `small`. The browser renders their metadata centroids as visible markers and gives all centroids an enlarged transparent pointer hit area. Polygon fills remain the authoritative country shapes.