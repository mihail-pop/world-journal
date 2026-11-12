# Map provider configuration

World Journal uses the configurable OpenFreeMap Liberty style as its initial external basemap and keeps country interaction independent through bundled Natural Earth geometry.

The provider style URL is configured through `MAP_STYLE_URL` in Django settings. All map labels follow App Font in Settings, using the same bundled web fonts or device fonts as the interface. `static/js/pages/map_fonts.js` removes the provider's glyph URL before its style loads, enabling MapLibre's built-in browser font rendering, and applies the selected family while retaining regular, bold and italic label variants. Font changes also update the retained map while it is detached on Settings. Country geometry, hit targets, fills, outlines and Adventure artwork remain bundled. Simple, Adventure and the provider fallback open without an external map or font service. Optional city and region labels use the same provider's vector tiles in every mode; starting in Simple/Adventure imports only place labels after the bundled map opens, without terrain imagery or remote sprites.

## Browser preferences

The map type selector now offers Terrain, Simple and Adventure. The
new `mapType` value is stored with existing v2 preferences, with the terrain flag
derived from it for compatibility. Older terrain-on/off choices retain their
meaning. [Adventure](adventure-map.md) documents the illustrated atlas style,
theme palettes, decorative artwork, unchanged interaction geometry and manual review.

Map preferences use the `world-journal:map-preferences:v2` localStorage key. Country names and the terrain basemap default on, capital names default off, and there is no default home country. Protected areas, buildings, land-use shading and places of interest default off; the remaining detail groups and other labels default on. `detailDefaultsVersion: 1` applies those four quieter defaults once when reading older preferences. Subsequent explicit changes are preserved. Other saved choices and the storage version remain unchanged. Legacy v1 values remain readable, with simple mode converted to terrain off. Invalid values and home-country codes absent from canonical metadata fall back safely.

The opening camera precedence is a valid country query, configured home country, saved viewport, then world view. Changing home country removes the separate `world-journal:map-viewport` value so the new home is visible on the next map initialization.

## Basemap layer adapter

The map controller owns country and capital labels. It suppresses matching provider labels to avoid duplicates using `isBasemapCountryLabel` and `isBasemapCapitalLabel` in `static/js/pages/basemap_features.js`. Classification uses label IDs or positive filter comparisons: a city rule excluding capitals must not be treated as a capital label, and a rule excluding countries must not be treated as a country label. Provider detail groups are isolated in the same module; water uses source-layer semantics (`water`, `waterway`, and `water_name`) with layer-ID terms as a fallback.

## Place labels

Terrain uses dark country text with white outlines and only slightly lighter
dark text for capitals and cities. The same styling applies to normal country
labels, enlarged hover labels, pointer names, capitals and settlements.
Simple, Adventure and the bundled provider fallback retain their existing sizes,
colors and capital placement.

`static/js/pages/map_labels.js` manages the Terrain hierarchy: country text grows
from 12 to 18 pixels between zooms 1 and 5, capitals from 12 to 16 between zooms
2.5 and 7, and cities from 10.5 to 15 between zooms 3 and 11. The selected app
font remains in use. Country hover stays 15% larger, and existing label zoom
limits, placement collisions and renderer fades remain active.

Capital names sit to the right of local concentric-circle icons. The dot and
label share one symbol so a collided-out label does not leave an orphaned dot.
Capital and city icons are drawn locally; no image provider is added. Provider
city-dot zoom limits remain unchanged. City dots have a one-pixel outline at
their displayed size instead of a thin subpixel ring, with a slightly larger
circle to separate them from map detail.

City & town names, enabled by default, independently controls the
existing OpenFreeMap city, town and village layers. Towns and villages appear
at closer zooms using the provider's existing rules and tiles. These labels no
longer depend on Other labels. Capital settlements are excluded from this group
even when the provider classifies them as towns or villages, keeping Capital
names as their single control.

Region names, disabled by default, separately controls the provider's
administrative-region labels, such as states, provinces and oblasts. It is saved
with the other browser map preferences. This group is independent of Other
labels and does not affect ocean/water names, city names or boundary lines.
Mixed provider place layers are partitioned once per style load, so provinces
inside a generic neighborhood/place layer also follow this control. Both parts
reuse the existing tile source, label appearance and zoom rules.

Both controls apply to Terrain, Simple and Adventure. Simple/Adventure place
text and dots follow their map palette, with city text kept smaller than their
capital names. `static/js/pages/place_labels.js` adds only the provider's place
symbols and required vector source when a bundled style needs them. Loading is
asynchronous, does not replace the map or camera, and respects map cleanup and
style changes. If the optional provider is unavailable, the bundled country map
and capital labels remain usable. With both controls off, a fresh bundled map
does not fetch provider place data.

For every loaded style, the adapter records each provider layer's original visibility before applying preferences. Re-enabling a feature restores that visibility while honoring other disabled groups. A `style.load` event clears the previous style snapshot, reinstalls application sources and layers idempotently, reapplies preferences, and restores selection state. Terrain off hides provider landscape/detail layers while independently enabled city and region labels remain visible; bundled sources stay installed.

## Country hover rendering

Hover fill and outline use `feature-state` paint expressions on the country's
promoted ISO alpha-2 feature ID. Their geometry and layer filters stay fixed while
the pointer moves. The old country's state is cleared and the new country's state
is set together before the next rendered frame, including all loaded polygon
parts and repeated world copies. Hover color and opacity transitions have zero
duration and delay.

Pointer movement keeps one latest position and at most one animation-frame
callback. Hit-testing runs once per frame rather than for every mouse event;
intermediate positions never queue old highlights. Clicks hit-test their own
position immediately, preferring the country under the pointer. In every mode,
moving onto water retains the last hovered country for 500 ms, then clears it.
Further movement over water does not restart that timer. Returning to land
cancels it, and entering another country switches hover immediately. Leaving the
canvas, moving the camera, or suspending/removing the map cancels pending expiry.
Every mode uses the normal arrow over land
and water, with a grabbing hand only after an actual drag starts. Pressing without
dragging keeps the arrow; releasing the mouse restores it immediately. Clicking
water during the 500 ms grace period opens the retained country's details, just
like a direct country click. After expiry, water clicks select nothing.

Leaving the canvas or losing window focus clears hover and cancels pending work.
Camera movement suppresses hover until it settles, then rechecks the stationary
pointer; the idle event also rechecks after new source tiles are rendered. Style
reloads restore paint state, and page cleanup cancels pending hover work before
removing the map. Selection, centroid hit targets, preset colors and themes keep
their existing behavior.

Terrain hides all bundled country outlines, including hover and selection
strokes, so only the provider's own boundaries are drawn. Hover enlarges a
country's visible label by 15%. Normal and enlarged labels are prepared from the
same centroid source; one `hoverLabel` paint flag switches their visibility
together only after the larger label is placed. Pointer movement never updates
source data or creates a new symbol, avoiding asynchronous gaps and fades during
rapid hovering. Normal label placement, zoom thresholds and map fades
stay unchanged. If the label is absent, collided out, or switched off, the name
appears above the pointer instead while zoomed out (below zoom 6). Closer zooms
keep the pointer clear for exploring cities. Both cues clear on movement, pointer exit and
navigation. Simple, Adventure and the bundled provider fallback retain their
existing border and fill highlights.

Manual check in Simple/Adventure: reload with Ctrl+F5, sweep rapidly across European countries, then
stop on one. Only the current country should be highlighted. Hover Russia,
Canada, and the United States at several zoom levels: loaded country parts should
change together, without a tile-by-tile fill animation. Move onto the
ocean and confirm hover stays on the last country, then move to another country
and confirm it switches. Leaving for the drawer, toolbar or outside the map
clears hover. Try dragging, zooming, microstate markers, themes, and Map → Journal → Map. In Terrain, verify
the enlarged label or pointer name, with no bundled borders. Also check hidden
country names, crowded labels, close zoom and provider fallback.

## Country selection rendering

Map now retains one detached canvas and its loaded country drawer across section navigation; returning through the header resumes its camera and content without reconstructing the map. See [Page memory](page-memory.md) for lifecycle details, limitations and manual checks. Older cleanup/navigation descriptions below and above describe the original phase implementation.

The clicked-country fill and outline also use fixed geometry with a separate
`selected` feature-state flag and zero-duration color/opacity transitions.
Switching countries clears the previous flag and sets the new flag before the
next frame, without rebuilding tiles or changing the independent hover flag.
Closing the drawer clears selection through the same path. Country URLs and
browser history use that path too, and source/style recreation restores the
current selected flag after installing the layers.

Manual check in Simple/Adventure: after Ctrl+F5, select a large country, then a neighboring country.
The previous fill and outline should disappear together across the visible
country, while the new selection appears together. Repeat quickly, close the
drawer, use Back/Forward, and return from Journal to Map with a selected country.
Also check simple mode and preset colors: removing selection should reveal the
underlying country styling evenly. Terrain selections should open the drawer
without adding a bundled country outline.

## 3D terrain availability

The Liberty style configured for Phase 2A was inspected on 2026-08-30. Its sources are an OpenMapTiles vector source and a Natural Earth shaded raster source. It does not contain a MapLibre-compatible `raster-dem` source or a hillshade layer. OpenFreeMap's official quick-start and self-hosting documentation do not document a compatible elevation source, elevation usage terms, or terrain attribution requirements.

Actual 3D elevation is not configured. The current interface's Terrain switch shows or hides the flat provider basemap, including its shaded relief image; it does not call `setTerrain`. Adding 3D elevation later requires a configurable provider definition containing:

- a documented, key-free or locally configured `raster-dem` tile source;
- its tile encoding and zoom limits;
- required attribution and usage terms;
- failure behavior suitable for MapLibre's `setTerrain` API;
- a self-hosting path that does not commit a massive elevation dataset.

Turning the terrain basemap off shows the bundled simple country map. Provider detail preferences remain saved for when the basemap is shown again.

## Country rendering, terrain and opening camera

Country rendering uses one fill and one outline, replacing the previous four fill passes and three line passes over the same geometry. `static/js/pages/country_paint.js` composes the base/preset/hover/selection colors and alpha before drawing. Terrain shows the provider map directly with label hover feedback and no bundled outlines. Explicit preset colors use 65% opacity. Simple, Adventure and the bundled provider fallback also use fill highlights at 32% on hover and 26% on selection. Selected outlines take priority over hover outlines in those modes. Four fill variants are stored per promoted ISO feature ID. Hover/selection flags choose a variant through a fixed paint expression, and palette/theme/terrain changes update feature state without replacing that expression or rebuilding country tile layouts. Country and centroid IDs, all country metadata, click hit targets, deep links, drawer behavior and persistent-map navigation remain unchanged.

The Natural Earth source and country identities are unchanged; the bundled geometry now uses coverage-preserving shared-border simplification (see country-data.md). MapLibre's prior default subpixel tolerance (0.375 pixel) is restored after the zero-tolerance experiment increased work at wide zooms. The source retains its normal zoom range and close-zoom detail; it is not forced into a coarse world tile or replaced by a lower-resolution dataset.

Terrain-off restores provider layer visibility suppression. Invisible basemap geometry no longer remains active through opacity overrides; it stops requesting/drawing tiles until needed again. Only changed visibility values are applied. Provider raster and symbol loading retain their normal fades, while application fill/outline changes keep zero transitions. The bounded viewport-based tile-cache budget is seven viewport sets instead of the default five, helping return zooms and short pans retain recently loaded tiles at some additional browser memory cost.

Home-country fitting uses symmetric padding with a closed drawer and does not retain drawer padding on the camera. Open drawers receive their normal camera space. Initial country fitting happens before asynchronous style/source loading, avoiding requests for both a provisional camera and a second fitted camera. World reset explicitly clears padding.

The experimental canvas visibility gate and per-render source-readiness check have been removed. New remote basemap tiles and labels can still arrive progressively in unvisited areas; these changes reduce local geometry/rendering work and restore normal provider loading transitions without promising that external resources arrive together.

Unchanged legend contents, favorite filters and theme paint settings are no longer rebuilt on ordinary selections or preference updates. Provider layer definitions are captured once per style; preference changes do not repeatedly serialize the whole map style.

Manual review (tests and browser checks remain with the user): hard-refresh once, pan and zoom repeatedly in Europe and around large countries, then repeat with terrain off/on and presets off/on. Sweep hover, switch selected neighbors and close the drawer. Check microstate hit targets and close-zoom borders; try preset selection/editing, home refresh, World reset and Map → Journal → Map. The country data and click behavior should remain the same, with fewer redraw stalls.

## Basemap feature controls

Settings → Preferences separates General map labels (country names, capital names, city names, region names and small-country markers, shared by every mode) from Terrain map details. Small-country markers default off, including for existing preferences without that field. This switch only hides the visible microstate dots; polygon selection and the enlarged centroid click targets remain available. Markers are installed hidden to avoid flashing before preferences are applied. The map's Display panel retains Terrain, Country names and Capital names plus its existing favorite/preset controls, with a More map options link to Settings.

Manual marker check: after Ctrl+F5, tiny-country dots should be hidden. Enable Small-country markers in General map labels and return to Map: the dots should appear in either view. Disable again and confirm they disappear, favorites/capital markers remain independent, and tiny countries are still selectable. The choice should survive refresh and section navigation. Browser and automated checks remain with the user.

The terrain section controls protected areas, vegetation/wetlands, shaded relief, water features, roads/railways/airports, buildings, land-use shading, administrative borders, points of interest and other labels. `static/js/pages/basemap_features.js` groups provider layers primarily by OpenMapTiles source-layer semantics, with conservative ID fallbacks. Group membership is computed once per style load. Unknown layers keep their provider visibility, and styles without a recognized group simply have nothing to hide for that preference. Multiple controls can affect a label (e.g. hiding transport hides road labels even when Other labels is on). Other labels affects provider text-bearing symbols except city/town/village and administrative-region labels; country, capital, city and region names have independent controls.

For the current Liberty style, protected areas controls the park fill and both park outlines. Vegetation controls wood, grass and wetland layers, leaving sand and ice alone. Relief controls the Natural Earth raster. These switches cannot remove colors already baked into that raster: turning off vegetation does not promise to remove every green pixel, and turning off water does not erase oceans from the relief image. Protected-area names delivered through POI layers follow Places of interest/Other labels, rather than the protected-area shading switch. Administrative borders controls provider boundaries only; selectable country outlines, hover, presets and hit targets remain intact. Buildings preserves the style's original visibility instead of forcing normally hidden layers on.

All controls share browser-local preference storage and a change event. A retained Map receives Settings changes without replacing its canvas or resetting the camera; detached maps apply visibility changes when resumed. The adapter hides layers through layout visibility and restores their original visibility, without changing styles, country geometry or paint transitions. Hiding only some vector layers reduces drawing work but does not stop fetching a vector source still used by visible layers.

Manual review (no automated tests/browser session run for this change): press Ctrl+F5, open Settings → Preferences, disable Protected areas and return to Map at a park/nature reserve. Its fill and outlines should disappear while forest shading remains. Toggle each detail group at an appropriate zoom; buildings and roads are clearest close up. Disable Other labels and confirm independently enabled country/capital labels remain. Toggle Terrain off/on in Display and confirm detail choices are retained. Check persistence on refresh, Map → Journal → Settings → Map with a selected country/video, and Settings at desktop/390px in all themes. Existing home-country, label and preset choices should be preserved.
