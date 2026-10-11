# Map provider configuration

World Journal uses the configurable OpenFreeMap Liberty style as its initial external basemap and keeps country interaction independent through bundled Natural Earth geometry.

The style URL and fallback glyph URL are configured through `MAP_STYLE_URL` and `MAP_GLYPHS_URL` in Django settings. The glyph endpoint is used only for application-owned country and capital labels when the provider style itself cannot be loaded; country geometry, hit targets, fills, and outlines remain bundled.

## Browser preferences

Map preferences use the `world-journal:map-preferences:v1` localStorage key and a value with `version`, `homeCountry`, `countryNames`, `capitalNames`, `water`, `terrain`, and `simpleMode` fields. Explicit defaults are country names and water on, with capital names, terrain, and simple mode off and no home country. Malformed values, obsolete versions, invalid field types, and home-country codes absent from canonical metadata fall back safely to those defaults.

The opening camera precedence is a valid country query, configured home country, saved viewport, then world view. Changing home country removes the separate `world-journal:map-viewport` value so the new home is visible on the next map initialization.

## Basemap layer adapter

The map controller owns country and capital labels. It suppresses matching provider labels to avoid duplicates and identifies water through source-layer semantics (`water`, `waterway`, and `water_name`) with documented layer-ID terms as a fallback. Detection is isolated in `isBasemapCountryLabel`, `isBasemapCapitalLabel`, and `isBasemapWaterLayer` in `static/js/pages/map.js` rather than spread through control handlers.

For every loaded style, the adapter records each provider layer's original visibility before applying preferences. Water restoration and leaving simple mode restore those exact values. A `style.load` event clears the previous style snapshot, reinstalls application sources and layers idempotently, reapplies preferences, and restores selection state. Simple mode hides all provider layers without changing styles, so the bundled sources remain installed and external attribution controls remain untouched.

## Country hover rendering

Hover fill and outline use `feature-state` paint expressions on the country's
promoted ISO alpha-2 feature ID. Their geometry and layer filters stay fixed while
the pointer moves. The old country's state is cleared and the new country's state
is set together before the next rendered frame, including all loaded polygon
parts and repeated world copies. Hover color and opacity transitions have zero
duration and delay.

Pointer movement keeps one latest position and at most one animation-frame
callback. Hit-testing runs once per frame rather than for every mouse event;
intermediate positions never queue old highlights. Clicks still hit-test their own
position immediately and do not depend on the hover callback.

Leaving the canvas or losing window focus clears hover and cancels pending work.
Camera movement suppresses hover until it settles, then rechecks the stationary
pointer; the idle event also rechecks after new source tiles are rendered. Style
reloads restore paint state, and page cleanup cancels pending hover work before
removing the map. Selection, centroid hit targets, preset colors and themes keep
their existing behavior.

Manual check: reload with Ctrl+F5, sweep rapidly across European countries, then
stop on one. Only the current country should be highlighted. Hover Russia,
Canada, and the United States at several zoom levels: loaded country parts should
change together, without a tile-by-tile fill animation. Move onto ocean, the
drawer, or toolbar and out of the map: the hover should clear. Try dragging,
zooming, microstate markers, simple mode, themes, and Map → Journal → Map. Browser
checks and automated tests are left to the user for this change.

## Country selection rendering

The clicked-country fill and outline also use fixed geometry with a separate
`selected` feature-state flag and zero-duration color/opacity transitions.
Switching countries clears the previous flag and sets the new flag before the
next frame, without rebuilding tiles or changing the independent hover flag.
Closing the drawer clears selection through the same path. Country URLs and
browser history use that path too, and source/style recreation restores the
current selected flag after installing the layers.

Manual check: after Ctrl+F5, select a large country, then a neighboring country.
The previous fill and outline should disappear together across the visible
country, while the new selection appears together. Repeat quickly, close the
drawer, use Back/Forward, and return from Journal to Map with a selected country.
Also check simple mode and preset colors: removing selection should reveal the
underlying country styling evenly. Tests and browser checks remain with the user.

## Terrain availability

The Liberty style configured for Phase 2A was inspected on 2026-08-30. Its sources are an OpenMapTiles vector source and a Natural Earth shaded raster source. It does not contain a MapLibre-compatible `raster-dem` source or a hillshade layer. OpenFreeMap's official quick-start and self-hosting documentation do not document a compatible elevation source, elevation usage terms, or terrain attribution requirements.

Terrain is therefore unavailable by default. The interface reports this honestly and does not use an undocumented demo endpoint. Enabling terrain later requires a configurable provider definition containing:

- a documented, key-free or locally configured `raster-dem` tile source;
- its tile encoding and zoom limits;
- required attribution and usage terms;
- failure behavior suitable for MapLibre's `setTerrain` API;
- a self-hosting path that does not commit a massive elevation dataset.

Simple mode temporarily suppresses terrain regardless of future provider configuration and restores the user's underlying terrain preference when the mode is left.
