# Adventure Mode

Choose **Map → Display → Map type → Adventure Mode**, or use the Map card in
Settings → Preferences. Terrain and No terrain remain available. The choice is
saved in existing browser-local preferences; old terrain-on/off preferences
become Terrain/No terrain without resetting any other choices.

## Art direction

An illustrated maritime atlas, with eight muted paper hues, engraved borders,
coastal ink rings, fine paper grain and hatching, repeated ocean-wave marks,
faint chart lines and sailing trails. Mountain, evergreen and sailing-ship
illustrations are original canvas artwork with ink contours, shaded faces,
snowcaps, hatching and pennants. A compass rose follows the map's bearing.
Country labels use spaced capitals and retain the existing available glyph fonts.

The dark theme uses a dusk-blue sea, warm sage/clay lands and ivory lettering;
light uses sea glass, pale parchment and brown ink; brown uses aged gold, warm
forest greens and a muted teal sea. The rest of the application's theme and
interface are unchanged. No whole-canvas CSS filter blurs the map or its labels.

Shared polygon edges build an adjacency graph once. Greedy coloring assigns
different base hues to neighboring polygons when their shared segments match.
Unshared ring edges form a coastline source; inland shared borders do not get
the coastal rings. The fill is opaque, so broad shoreline strokes drawn beneath
it appear outside land. Country outlines remain on top of the texture.

The world geometry, ISO identities, accuracy and detail are unchanged. The
mountains/trees are sparse illustrations around approximate broad regions, not
a terrain/forest dataset. Ships and trails are ornament, not live shipping data
or actual routes. They fade at close zooms; country labels take placement
priority over illustration symbols. No fictional countries or islands are added.

## Behavior and implementation

`static/js/pages/adventure_map.js` owns the palettes, artwork, topology and extra
layers. They are installed lazily when Adventure is first selected and reuse
the current MapLibre map. Their textures/sprites are generated once per theme,
using a fixed seed, and reused; no image service, new feed, map provider, font
dependency, API key, Python package or database migration is required. Existing
glyph/provider configuration and attribution remain intact.

All provider terrain layers are hidden in Adventure. The original country fill
still uses fixed hover/selection feature-state expressions. Adventure changes
the base fill per country; preset colors retain the existing blend and take
priority. Actual click targets, drawer tabs, home/deep links, favorites, capital
labels and country markers use the same sources/controllers. Decorations cannot
intercept clicks because hit testing only queries the original interaction
layers. The compass/frame are pointer-transparent and the compass hides while
the country drawer is open.

Returning to the other map types hides the extra layers and restores normal
paint and label styling without recreating the map, camera or country drawer.
Settings changes also work with the detached retained Map. Extra line/pattern
passes do add some rendering work while Adventure is active; no performance
benchmark or browser verification was performed. Normal map types keep these
layers hidden, and do not create the artwork/topology until it is first needed.

## Manual review

Restart the server, reload with Ctrl+F5 and select Adventure Mode in Display.

1. View the whole world, then zoom into Europe, South America and Asia. Check
   coastline rings, different neighboring colors, paper texture, mountains,
   forests, ships and label legibility. Close zooms should quiet the decoration.
2. Sweep hover, select/close countries, pan/zoom and try tiny countries. Their
   original shapes, hit targets, selection and news behavior should remain.
3. Try each theme; then a color preset and the preset editor. Groups/legend and
   hover/selected states should remain distinguishable from the artwork.
4. Toggle country/capital labels and country markers. Switch Terrain → Adventure
   → No terrain → Terrain; terrain detail preferences must remain intact.
5. Choose Adventure from Settings while Map is retained. Return to Map and check
   it updates without losing its camera or selected country. Refresh and check
   the saved type. Rotate the map and check the compass rose follows north.
6. Check desktop and 390px layouts with a drawer, legend and playing video.

Tests and browser verification are left to the user, as requested.

Rendering APIs: https://maplibre.org/maplibre-style-spec/layers/ and
https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#addimage
