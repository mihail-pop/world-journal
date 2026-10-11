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
.\.venv\Scripts\python.exe -m pip install -r tools\requirements-country-data.txt
.\.venv\Scripts\python.exe tools\build_country_data.py
```

The script uses optional, pinned Shapely/NumPy maintainer dependencies for geometry generation. They are not app dependencies: running the server only needs the already bundled GeoJSON. Downloads and shapefile/metadata parsing still use the Python standard library. The generator downloads the tagged SHP, DBF, and version files, verifies their hashes, and parses the aligned 258 source records. It assembles the unsimplified country polygons before simplifying the entire polygon coverage using Shapely/GEOS's coverage-preserving Visvalingam–Whyatt algorithm. Its 0.03 tolerance is based on triangle area and is not equivalent to the old 0.015-degree distance tolerance. This setting keeps the browser asset near its previous point budget. Shared borders are simplified together, rather than independently for each country. Source coordinates are aligned on a 1e-8-degree grid and the simplified result is rounded on a common four-decimal grid. It writes:

- `data/countries.json`
- `static/data/countries.geojson`

Generation fails unless it produces exactly 238 unique ISO-backed metadata and geometry records with an exact join. Before simplification, GEOS repairs invalid polygon structure already present in the pinned source: a self-crossing ring in Egypt and touching/overlapping same-country parts after merging Brazil/Kazakhstan records. It refuses to export source polygons still invalid after repair, mismatched source edges, invalid simplified/rounded coverage, missing countries, or removed island components. Country names, ISO identities, bounds, centroids, microstate hit targets and the source's territorial policy remain unchanged. This addresses gaps/overlaps introduced by independent simplification; it does not align the geometry to the separate external basemap or fill deliberately excluded territories.

The regenerated browser asset contains 141,626 coordinate points and is 2,683,598 bytes, versus 148,304 points and 2,807,966 bytes previously (about 4.5% fewer points and 4.4% smaller). No simplification runs in the browser. Browser performance and visual acceptance remain manual checks, not measured results. After Ctrl+F5, inspect shared borders at several zoom levels (especially the locations where seams were visible), enclaves such as Lesotho, islands/microstates, hover/selection and presets. A separate provider's coastlines/boundaries can still differ, and deliberately excluded territories remain unfilled.

## ISO policy and exceptions

A source record is selectable only when Natural Earth's `ISO_A2_EH`, `ISO_A3_EH`, and `ISO_N3_EH` fields form a complete ISO 3166 identity. Duplicate records for France/Clipperton Island, Kazakhstan/Baykonur, Brazil/Brazilian Island, and Australia/its grouped dependencies are merged into one MultiPolygon per ISO alpha-2 code.

The following source records are not assigned invented ISO codes and are not selectable: Dhekelia Sovereign Base Area, Somaliland, Kosovo (`XK` is user-assigned, not ISO 3166), US Naval Base Guantanamo Bay, Northern Cyprus, Cyprus No Mans Area, Siachen Glacier, Akrotiri Sovereign Base Area, Southern Patagonian Ice Field, Bir Tawil, Spratly Islands, Bajo Nuevo Bank, Serranilla Bank, and Scarborough Reef.

Natural Earth's Admin 0 countries theme groups some dependencies with administering countries. The application preserves that source policy instead of synthesizing separate boundaries from unrelated data.

## Small-country interaction

Records carrying Natural Earth's `TINY` classification are marked `small`. The browser renders their metadata centroids as visible markers and gives all centroids an enlarged transparent pointer hit area. Polygon fills remain the authoritative country shapes.

## National capital data

World Journal also derives a small runtime GeoJSON file from Natural Earth's `ne_10m_populated_places` dataset at the same immutable `nvkelso/natural-earth-vector` v5.1.2 repository tag.

- Dataset: Natural Earth `ne_10m_populated_places`
- Resolution: 1:10m
- Dataset version: 5.1.2
- Source DBF: `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/10m_cultural/ne_10m_populated_places.dbf`
- Source version file: `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/10m_cultural/ne_10m_populated_places.VERSION.txt`
- DBF SHA-256: `eff834a8727e06f28fc52b04393c462d074aecf9a7acd1b870e766240a995b6c`
- Version-file SHA-256: `0c9a9d43610d66f4cc3f42da08cae044483de25894a9daf9dc6a76ff75ca9327`
- License: public domain

The generator selects records only when `ADM0CAP` is `1` and `ISO_A2` exactly joins the canonical country metadata. Runtime properties come from `NE_ID`, `NAME_EN` with `NAMEASCII` as a fallback, and `ISO_A2`; coordinates come from `LONGITUDE` and `LATITUDE`. `CAPIN` is used only by generation validation and reporting to preserve legitimate multiple-capital cases without adding unused runtime data.

Natural Earth marks 200 records as national capitals. The strict ISO join includes 198 records across 194 countries. It preserves all source-designated capitals for Bolivia (La Paz and Sucre), Côte d'Ivoire (Abidjan and Yamoussoukro), and South Africa (Bloemfontein, Cape Town, and Pretoria). Pristina/Kosovo and Hargeisa/Somaliland are excluded because their source records use `ISO_A2=-99`; no code or country assignment is guessed. Countries and territories absent from this Natural Earth national-capital classification are left without a capital marker rather than supplemented from another source.

The generated `static/data/capitals.geojson` is 29,395 bytes. It contains only stable feature IDs, canonical joined ISO alpha-2 codes, display names, and point coordinates needed by the runtime map layers.
