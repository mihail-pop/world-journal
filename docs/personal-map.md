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

Favorite a country in its drawer. Favorites appear as hearts on the map and in the Display panel's jump selector. The selector and favorite actions become available after saved map data loads; failure leaves the ordinary map usable and offers Retry.

Open Display → Manage color presets, or Settings → Manage color presets. Create a named preset and add color groups. Each group has a searchable multi-country selector; a country can belong to only one group. Optionally enter a default color for other countries. Add/remove groups, save, activate, duplicate, rename or delete with confirmation. Groups with equal colors are combined when reloaded. Existing presets keep their data; no schema migration is needed. The Display selector can also activate a preset or turn colors off.

Preset fills use an application-owned layer below hover/selection. Tiny-country markers also use preset colors. Favorites are a separate centroid layer. Layers are reapplied on style load and theme changes, including the bundled fallback style. Saved data is fetched on each map mount; changes in another browser are visible on reload/re-entry rather than pushed live.

Articles remain the default country tab. Opening Notes lazily fetches the overview preview, up to three main-entry images, and up to six saved entries. Returning to that loaded tab does not fetch again. Country changes, drawer closure and page cleanup cancel requests and invalidate pending results. Notes use the same Journal renderer; long overview text is bounded to a preview and links to the full entry.

Create overview note explicitly creates and selects an ordinary country-tagged Journal entry, then opens its editor. Canceling that editor leaves the newly created overview entry in the Journal. Choose note can select an existing country-tagged entry or clear the profile. A single entry can be the featured overview of one country. Add pictures from the entry's detail page, then return to the country's Notes tab. `/?country=RO&section=notes` opens it directly.

## Manual acceptance

No new tests, test-suite runs or browser checks were performed, as requested. The additive migration was generated and applied.

1. Favorite Romania, refresh and reopen it: the favorite persists. Display's favorite selector jumps to it; removing it clears the heart and selector entry.
2. Create a preset with two different country colors. Activate it, return to Map and switch terrain on/off; both colors remain, and hover/selection outlines are visible. Try a tiny country too.
3. Add a default color; countries without rows use it. Clear the default and save; unassigned countries keep normal map styling.
4. Duplicate and rename the preset; changes to the copy do not change the original. Activate then delete a preset with confirmation; the ordinary map returns and Journal/favorites remain.
5. Open Notes and create an overview entry with Markdown and a main-section picture. Return via the country link: the preview, picture and saved-entry list appear. Choose another entry or clear the selection; previous entries are kept.
6. Switch countries quickly during Notes loading, close the drawer, and use back/forward: another country's late results must never appear. Map/Journal/Settings navigation should keep the player running.
7. Check dark/light/brown themes and a 390px window: controls, preset forms and the drawer should remain usable.

Custom per-country preset icons/flag uploads are deferred; colors and favorite hearts cover the initial preset workflow. Country fact data, source settings, backup/import and statistics remain separate implementation phases.

## Map selection editor

Choose **Select on map** from a saved preset, **Save & select on map** from its regular editor, or **Display → Create preset on map**. Direct links use `/?edit_preset=<UUID>` (or `new`). The regular editor saves its fields before opening the map, so those edits are included.

The preset drawer replaces the country drawer. Clicking an unassigned country adds it to the active group without loading its news or videos. Clicking an assigned country switches to that group. Add color activates a new group. Color changes preview immediately; matching colors merge. Country chips remove assignments; removing a group removes its assignments. The searchable selector can also select several countries and disables countries in other groups. To move a country, remove it from its old group first.

**Save & use colors** saves all assignments atomically and activates the preset. **Discard changes** restores saved map colors and exits. The close button returns to the ordinary map while retaining the draft in the current tab. HTMX navigation to Journal/Settings and browser back/forward retain drafts with the Map workspace. Unsaved drafts are memory only; save before refreshing or closing the tab. The browser warns when leaving with an unsaved draft. A preset changed in another editor produces a conflict message and an explicit discard-and-reload action, rather than silently replacing newer saved data.

The editor uses the existing MapPreset/PresetCountry tables and validates the same country identities and six-digit colors. No production data is created until a save (apart from the explicitly labeled regular editor save-and-open action).

### Manual checks for the updated workflow

1. On the regular preset page, choose Romania and Bulgaria for one color and France/Germany for another. Save and reopen: all four assignments should persist in their groups.
2. Open Select on map, add a new color, and click two unassigned countries. Their fill colors should preview immediately. Clicking a previously colored country must switch to its group without recoloring it.
   Also open an existing preset's Select on map link before visiting Map in a fresh session, and refresh that link directly. The drawer must open while the renderer loads; existing presets do not need to be recreated. Initialization or loading failures show a visible Retry button.
3. Change a group's color; all its countries should update. Set it to another group's color: the groups should merge. Remove a country chip, then assign it to a different color. Remove a group, then add another. Tiny-country targets should also work.
4. Save & use colors, exit, refresh, and reopen: colors should persist. Make a different draft and discard: saved colors should return. Try a duplicate name and a preset modified in another editor: errors should retain the draft.
5. Switch to Journal/Settings and return while editing. Countries, active group and camera should remain. Check Back/Forward between ordinary map and preset mode. Country clicks in preset mode should not fetch news/video feeds.
6. Open a country normally. Its name opens saved Journal entries tagged with that country; ordinary text mentions do not match. Overview observation years are hidden, and the larger flag uses the existing vector SVG with an offline emoji fallback.
7. Check dark/light/brown themes, a 390px window, and a playing/minimized player: the preset drawer uses the same responsive placement as country details.

Only source review and `git diff --check` were performed; no tests or browser checks were run, as requested.
