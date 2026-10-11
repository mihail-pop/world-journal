# Personal map data (Phase 6)

Favorites, color presets and country overview notes are shared SQLite data. Theme, viewport and display preferences remain browser-local. No new dependencies are needed.

## Data

- `CountryFavorite`: one row per ISO country, with its creation timestamp. Favorites do not affect news eligibility or ranking.
- `MapPreset`: stable UUID, unique name, description, optional default color and creation/update timestamps.
- `PresetCountry`: one color assignment per preset/country pair, enforced by a database uniqueness constraint. Colors are validated six-digit hex values, not arbitrary CSS.
- `MapPersonalState`: singleton row at key 1 with a nullable active-preset foreign key. Deleting the active preset clears the selection; one preset is active at a time.
- `CountryProfile`: one selected overview Journal entry per country. The entry retains its normal countries, subsections and attachments. Clearing/changing the selection does not delete an entry. Deleting that entry clears the profile reference.

The migration depends on the existing Journal migration and adds tables without replacing country or Journal data. Apply it with the workspace interpreter: `.\.venv\Scripts\python.exe manage.py migrate`.

## User flows

Favorite a country in its drawer. Favorites appear as rings on the map and in the Display panel's jump selector. The selector and favorite actions become available after saved map data loads; failure leaves the ordinary map usable and offers Retry.

Open Display → Manage color presets, or Settings → Manage color presets. Create a named preset, choose countries and colors, and optionally enter a default color. Add/remove rows, save, activate, duplicate, rename or delete with confirmation. The Display selector can also activate a preset or turn colors off.

Preset fills use an application-owned layer below hover/selection. Tiny-country markers also use preset colors. Favorites are a separate centroid layer. Layers are reapplied on style load and theme changes, including the bundled fallback style. Saved data is fetched on each map mount; changes in another browser are visible on reload/re-entry rather than pushed live.

Articles remain the default country tab. Opening Notes lazily fetches the overview preview, up to three main-entry images, and up to six saved entries. Returning to that loaded tab does not fetch again. Country changes, drawer closure and page cleanup cancel requests and invalidate pending results. Notes use the same Journal renderer; long overview text is bounded to a preview and links to the full entry.

Create overview note explicitly creates and selects an ordinary country-tagged Journal entry, then opens its editor. Canceling that editor leaves the newly created overview entry in the Journal. Choose note can select an existing country-tagged entry or clear the profile. A single entry can be the featured overview of one country. Add pictures from the entry's detail page, then return to the country's Notes tab. `/?country=RO&section=notes` opens it directly.

## Manual acceptance

No new tests, test-suite runs or browser checks were performed, as requested. The additive migration was generated and applied.

1. Favorite Romania, refresh and reopen it: the favorite persists. Display's favorite selector jumps to it; removing it clears the ring and selector entry.
2. Create a preset with two different country colors. Activate it, return to Map and switch terrain on/off; both colors remain, and hover/selection outlines are visible. Try a tiny country too.
3. Add a default color; countries without rows use it. Clear the default and save; unassigned countries keep normal map styling.
4. Duplicate and rename the preset; changes to the copy do not change the original. Activate then delete a preset with confirmation; the ordinary map returns and Journal/favorites remain.
5. Open Notes and create an overview entry with Markdown and a main-section picture. Return via the country link: the preview, picture and saved-entry list appear. Choose another entry or clear the selection; previous entries are kept.
6. Switch countries quickly during Notes loading, close the drawer, and use back/forward: another country's late results must never appear. Map/Journal/Settings navigation should keep the player running.
7. Check dark/light/brown themes and a 390px window: controls, preset forms and the drawer should remain usable.

Custom per-country preset icons/flag uploads are deferred; colors and favorite rings cover the initial preset workflow. Country fact data, source settings, backup/import and statistics remain separate implementation phases.
