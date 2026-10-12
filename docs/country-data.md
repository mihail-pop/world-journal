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

The script uses optional, pinned Shapely/NumPy maintainer dependencies for geometry generation. They are not app dependencies: running the server only needs the already bundled GeoJSON. Downloads and shapefile/metadata parsing use the standard library. The generator verifies the tagged SHP, DBF and version files and parses all 258 source records. It assembles the polygons before simplifying the entire shared coverage using GEOS's coverage-preserving Visvalingam–Whyatt algorithm, with triangle-area tolerance 0.03. Source coordinates are aligned on a 1e-8-degree grid and rounded on a common five-decimal grid; the finer output precision preserves the Bir Tawil/Sudan boundary. It writes:

- `data/countries.json`
- `static/data/countries.geojson`

After regenerating country geometry, also regenerate Adventure's derived
color asset with `.\.venv\Scripts\python.exe tools\build_adventure_data.py`.
See [Adventure](adventure-map.md) for the precomputed hues and provenance.

Generation requires 238 unique ISO-backed entries plus 14 reviewed custom entries with exact geometry joins. GEOS repairs the existing self-crossing ring in Egypt and touching/overlapping merged Brazil/Kazakhstan parts. Export refuses invalid source/simplified/rounded coverage, missing identities or removed island components. The original ISO identities and Natural Earth territorial policy remain unchanged. The previously excluded non-ISO polygons are now filled and selectable; see [Custom territories](custom-territories.md). This does not align the separate external basemap's geometry.

The combined browser asset contains 142,006 coordinate points and is 2,976,905 bytes, versus 141,626 points and 2,683,598 bytes before adding custom territories. No simplification runs in the browser. Performance and visual acceptance remain manual checks. After Ctrl+F5, inspect shared borders, enclaves such as Lesotho, narrow Cyprus areas, Bir Tawil, islands/microstates, hover/selection and presets. A separate provider's coastlines/boundaries can still differ.

## ISO policy and exceptions

Official entries require complete Natural Earth `ISO_A2_EH`, `ISO_A3_EH` and `ISO_N3_EH` identities. Duplicate France/Clipperton, Kazakhstan/Baykonur, Brazil/Brazilian Island and Australia/dependency records are merged per ISO alpha-2 code. The remaining records use reviewed local keys from `data/custom_territories.json`, explicitly marked custom without an ISO alpha-3 or flag. These keys preserve the existing two-character routing/storage layout and are not presented as official ISO assignments.

All 14 formerly excluded records are selectable: Dhekelia, Somaliland, Kosovo, Guantanamo Bay Naval Base, Northern Cyprus, the Cyprus UN buffer zone, Siachen Glacier, Akrotiri, the disputed Southern Patagonian Ice Field section, Bir Tawil, Spratly Islands, Bajo Nuevo Bank, Serranilla Bank and Scarborough Shoal. Custom identity, local fact editing, source corrections and geographic scope are documented in [Custom territories](custom-territories.md).

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
