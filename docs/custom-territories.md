# Custom territories

The pinned Natural Earth Admin 0 countries file contains 258 source records. The original 238 ISO-backed map entries merge six duplicate/dependency records and omitted 14 records without a complete ISO identity. Those 14 are now bundled, filled and selectable in every map type, including Simple and Adventure.

|Local key|Map name|
|---|---|
|XK|Kosovo|
|XC|Northern Cyprus|
|XL|Somaliland|
|XI|Siachen Glacier|
|XU|United Nations Buffer Zone in Cyprus|
|XA|Akrotiri Sovereign Base Area|
|XD|Dhekelia Sovereign Base Area|
|XG|Guantanamo Bay Naval Base|
|XP|Southern Patagonian Ice Field (disputed section)|
|XB|Bir Tawil|
|XV|Spratly Islands|
|XN|Bajo Nuevo Bank|
|XE|Serranilla Bank|
|XR|Scarborough Shoal|

These `X…` values are stable application keys, **not official ISO codes**. Existing two-character routing/storage fields are reused for compatibility with deep links, favorites, presets, country-tagged Journal entries, news and rolling archives. Custom metadata explicitly carries `is_custom: true`, an empty ISO alpha-3/flag, and the exact reviewed Natural Earth record ID. No FlagCDN request is made for them. The strict original 238 ISO identities remain unchanged.

This fills every omitted polygon in this pinned dataset. Natural Earth's additional disputed-area themes include other overlapping claims and breakaway regions, which are already inside country shapes here. They are not cut out or overlaid as competing selectable polygons. Taiwan and Western Sahara were already included through their ISO-backed entries. The app retains [Natural Earth's de facto boundary policy](https://www.naturalearthdata.com/about/disputed-boundaries-policy/), rather than assigning sovereignty through these local keys. The snapshot does not update disputed boundaries automatically.

## Facts and editing

Select a custom area and open Overview. The Custom territory label and Edit details button open a shared Django form for name, population, area in km², administrative center/capital, languages, currency, government and notes. Blank fact fields use the bundled value where available; explicit zero is retained. The label and editor are also available on Countries. Changed names update Journal country choices and `[[country]]` references without changing IDs or relationships. Canonical bundled names remain valid references and are used for news queries/matching. Retained Map/Countries screens update their labels and invalidate Overview content after saves and backup imports; polygon geometry and the map camera are retained.

Kosovo ([Q1246](https://www.wikidata.org/wiki/Q1246)), Northern Cyprus ([Q23681](https://www.wikidata.org/wiki/Q23681)) and Somaliland ([Q34754](https://www.wikidata.org/wiki/Q34754)) have a separately bundled Wikidata snapshot, acquired with reviewed entity mappings rather than ISO claims. Refresh it with:

```powershell
.\.venv\Scripts\python.exe tools\build_territory_facts.py
```

The existing statement/rank/date/unit rules are reused. Browsing remains offline for facts. Population, area and other missing fields for the remaining areas can be entered locally; whole-glacier, archipelago or base-group figures are not assumed to describe the particular polygon. Natural Earth's Spratly record has incorrect `NAME_EN` and `WIKIDATAID` values pointing to Wake Island. Its reviewed map name is Spratly Islands, and that erroneous Wikidata mapping is deliberately not used.

`countries.TerritoryDetails` stores user edits in SQLite; it only accepts custom country parents and updates their display names. Portable ZIP format 5 includes these details while still accepting formats 1–4. Existing local edits win during merge imports, as with the other stored records. Bundled facts and geography remain application assets.

## Geometry and colors

`tools/build_country_data.py` joins all 14 definitions by pinned `NE_ID` and checks `ADM0_A3`, then simplifies the complete shared coverage together. A common five-decimal output grid preserves the Bir Tawil/Sudan boundary; rounding that coverage at four decimals produced invalid edges. The generator retains its validity and island-component safeguards. The resulting asset has 142,006 points and 2,976,905 bytes, compared with 141,626 points and 2,683,598 bytes previously. No geometry processing is added to the browser.

`data/adventure-country-colors.json` freezes the previous 238 Adventure hues. The Adventure generator retains those hues and assigns compatible hues to the added areas using the same eight-color palette. Rebuild the derived asset after geometry generation:

```powershell
.\.venv\Scripts\python.exe tools\build_adventure_data.py
```

Capital markers retain the existing ISO-joined Natural Earth capital dataset. New territory capitals can appear in Overview without a separate map marker.

## Manual review

- Restart the server and Ctrl+F5. Inspect Kosovo, northern Cyprus (including the buffer/base areas), Somaliland, Siachen, Bir Tawil and southern Patagonia in Simple and Adventure. Previously unfilled land should now be colored/selectable. Reefs and banks require close zoom; optional small-country markers remain off by default.
- Open Overview, edit a disposable territory name/fact and save. The success notice should appear, and the updated label/fact should appear on Map and Countries. Switch pages and return; the camera and current country should remain intact.
- Favorite a custom area, assign it a preset color and create/tag a Journal entry. Verify both the canonical and locally edited names in `[[…]]` references.
- Inspect the 238 original country colors in Adventure and active border highlights. Existing hues are preserved. Check the narrow Cyprus buffer zone and Bir Tawil/Sudan borders at close zoom.
- Export a ZIP and review its import preview. Custom territory edits should be listed; importing an older archive should continue to work.

No browser acceptance, Django checks or test suite were run for this change, per the user's requested workflow. Database migrations and the asset generators were run.
