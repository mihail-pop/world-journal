# Adventure

Choose **Map → Display → Map type → Adventure**, or use the Map card in
Settings → Preferences. Terrain and Simple remain available. The choice is
saved in existing browser-local preferences; old terrain-on/off preferences
become Terrain/Simple without resetting any other choices. Stored `plain` and
`adventure` values are unchanged, so renaming the labels needs no migration.

## Art direction

An illustrated maritime atlas, with eight muted paper hues, engraved borders,
fine paper grain and hatching, repeated ocean-wave marks,
faint chart lines and sailing trails. Mountains, snowy peaks, evergreen forests,
tropical groves, dunes, sailing ships, sea serpents, dragons, unicorns, mossy
golems, spirit foxes, volcanoes and tornadoes are original
canvas artwork with matching ink contours, shaded faces and hatching. A compass
rose follows the map's bearing. The eight country colors in every theme and the
country adjacency coloring are unchanged by the artwork refinements.
Country labels use spaced capitals and retain the existing available glyph fonts.

The dark theme uses a dusk-blue sea, warm sage/clay lands and ivory lettering;
light uses sea glass, pale parchment and brown ink; brown uses aged gold, warm
forest greens and a muted teal sea. The rest of the application's theme and
interface are unchanged. No whole-canvas CSS filter blurs the map or its labels.

The maintainer generator precomputes the existing adjacency coloring with the
same edge ownership, FNV-1a preference and greedy ordering; country hues remain
unchanged. Decorative coast lines and halos are removed entirely. Actual
country borders, coast geometry and click targets remain unchanged.

The original ISO identities and eight-color palette are preserved. The map also
fills all 14 reviewed [custom territories](custom-territories.md), and their hues
are chosen without recoloring the original 238 countries. The
mountains/trees are sparse illustrations around approximate broad regions, not
a terrain/forest dataset. Snowy peaks are placed in Alaska, Greenland, Iceland,
the Rockies, Alps, Scandinavia, Himalayas and southern mountain ranges. Dunes
mark the Sahara, Arabian Peninsula, Namib, Atacama, Gobi and inland Australia;
tropical groves replace evergreens around the Amazon, Congo and Southeast Asia.
The mountain formerly in the Mozambique Channel is relocated to Madagascar's
central highlands at 47°E, 20°S. All terrain illustration anchors, as well as
land creatures, are checked against the bundled country polygons.
The dunes contain only sand, with their former sun circle removed. Sea serpents
remain in open ocean. Dragons are inland in China and southern Africa; unicorns
appear in Germany/Canada, golems in the American Southwest/Mongolia, and spirit
foxes in northern Finland/Siberia. Land-creature anchors are checked against the
actual bundled country polygons, including holes; sea-serpent anchors must lie
outside them. These sparse decorative positions are cached with the map. Volcanoes
mark broad volcanic regions in Iceland, Mexico, the Andes, East Africa, Japan,
Java and Kamchatka, replacing some nearby mountain symbols. Two tornado motifs
sit in the American Great Plains and inland Argentina. These are illustrations,
not live weather or eruption reports; their anchors are also checked against land.

Ships and trails are ornament, not live shipping data or actual routes. The
South Atlantic–Indian Ocean trail travels south of Africa's cape and Madagascar.
The North Atlantic trail ends offshore of Portugal; a Pacific passage extends
across the dateline using two joined segments, avoiding a line through land.
Gentle corner cutting smooths those offshore control paths. Trails keep their
existing close-zoom fading. Boats and sea creatures retain their previous size
and full-opacity behavior at every zoom. Land illustrations use a separate
symbol layer: hidden below zoom 3.2, fading to full opacity at 3.8 (roughly a
continental view), then fading out between 5.3 and 6.5 for close country detail.
These zoom levels are approximate because viewport size affects visible extent.
Both layers allow overlap and ignore placement; labels are drawn above them.
No fictional countries or islands are added.

## Behavior and implementation

Adventure hover and selection borders use separate line layers above ordinary country borders and artwork, with selection drawn last. This prevents a neighboring country's thin dark stroke from leaving a hollow center in a bright shared edge. Existing theme-specific highlight colors and widths are preserved. The layers reuse the bundled country source and update through feature state, without per-hover filters, sorting, or geometry changes. Terrain and Simple keep their existing border styling.

`static/js/pages/adventure_map.js` owns the palettes, artwork and extra
layers. They are installed lazily when Adventure is first selected and reuse
the current MapLibre map. Their textures/sprites are generated once per theme,
using a fixed seed, and reused; no image service, new feed, map provider, font
dependency, API key, Python package or database migration is required. Existing
glyph/provider configuration and attribution remain intact.

Simple and Adventure start with a bundled style instead of waiting for the
external Terrain style to download. The provider style is requested on the first
switch to Terrain, and its usual style-load handler restores application layers,
selection, favorites and preferences. After loading, other types hide provider
layers as before. Application labels still use the configured glyph endpoint.

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
layers hidden, and do not create the artwork until it is first needed.

Chart layers stop at the zoom where their opacity reaches zero. Point sources
use overzooming to keep water illustrations at close zooms. Country label layout
is updated only when its styling mode changes or layers are recreated. Country
geometry resolution, paper texture and country colors are preserved. Land and
water illustrations share one point source.

## Regenerating country hues

`static/data/adventure-map.json` bundles only precomputed country colors, about
1.8 KB. Its source SHA-256 records the country geometry it was derived from.
Regenerate it after regenerating country geometry:

```powershell
.\\.venv\\Scripts\\python.exe tools\\build_adventure_data.py
```

Generation uses only the Python standard library, reads local GeoJSON without
network access and writes only the Adventure asset. No decorative coast data,
sources, layers or generation routines remain. Ctrl+F5 still reloads browser
resources and reconstructs the map; Simple/Adventure avoid the unnecessary
initial Terrain style request. No browser benchmark was run.

## Favorites

Adventure favorites use the existing licensed Heroicons heart silhouette with
an original red pigment wash, fine hatching, paper flecks and ink edging. The
textured heart appears only on map favorites. The country drawer retains its
normal interface heart in every map type. Unfavorited countries retain their
outline heart; Terrain/Simple keep their original map hearts. Favorite data and
click behavior are unchanged.

Favorite hearts sit just above country names with about two pixels of clearance
at the largest label size, using one fixed position at every zoom. Spacing still
accounts for estimated wrapped name rows and the map type's maximum label size
(16 in Adventure, 14 in Terrain/Simple). Turning names off does not move the
hearts. The former home-country
adventurer/slime artwork is removed. Home-country navigation remains unchanged.

## Manual review

Restart the server, reload with Ctrl+F5 and select Adventure in Display.

1. View the whole world, then zoom into Europe, South America and Asia. Check
   different neighboring colors, paper texture, mountains, forests, ships and
   label legibility. No decorative offshore lines or halos should appear around
   continents or islands at any zoom; ordinary country borders should remain.
2. Sweep hover, select/close countries, pan/zoom and try tiny countries. Their
   original shapes, hit targets, selection and news behavior should remain.
3. Try each theme; then a color preset and the preset editor. Groups/legend and
   hover/selected states should remain distinguishable from the artwork.
4. Toggle country/capital labels and country markers. Switch Terrain → Adventure
   → Simple → Terrain; terrain detail preferences must remain intact.
5. Choose Adventure from Settings while Map is retained. Return to Map and check
   it updates without losing its camera or selected country. Refresh and check
   the saved type. Rotate the map and check the compass rose follows north.
6. Check desktop and 390px layouts with a drawer, legend and playing video.
7. Find dunes in the Sahara/Australia, snowy peaks in the Alps/Himalayas, tropical
   groves in the Amazon/Congo, sea creatures in the Atlantic/Pacific and land
   creatures in the regions above. Dunes should have no sun circle. Check
   the trail around southern Africa and across the Pacific, then compare pan/
   zoom smoothness and colors with the previous version in all three themes.
8. Favorite countries with short and long names. Hearts should clear their names
   in Terrain, Simple and Adventure, at world and regional zooms. Toggle names
   and switch themes. No adventurer/slime should appear beneath the home country.
9. Zoom from a world view into Europe: land illustrations should fade in around
   the continental view and fade away at close country detail. Boats and sea
   creatures should keep their prior visibility. Inspect volcano/tornado regions.
10. Start in Adventure or Simple with Ctrl+F5, then switch to Terrain and back.
    Check startup, labels, provider attribution, selected country and favorites.
    Hearts should sit just above Romania's name with a small gap throughout
    zooming, without jumping between positions. The drawer heart should keep
    normal styling. Check all three map types and themes, and Madagascar's mountain.

Tests and browser verification are left to the user, as requested.

Rendering APIs: https://maplibre.org/maplibre-style-spec/layers/ and
https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#addimage
