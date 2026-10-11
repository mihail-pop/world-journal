# Interface refresh

This pass changes presentation using Django templates, one shared CSS layer (`static/css/ui.css`), reusable inline SVG icons, and the existing JavaScript modules. It adds no dependencies, migrations or frontend build. `APP_CONTEXT.md` is unchanged.

Settings uses direct, HTMX-enabled links for Preferences, Backup, Sources and Information. Source toggles still belong to the shared preferences form; refreshing one feed remains a separate action. Export remains an ordinary download and import retains its preview and explicit confirmation.

The Journal keeps search visible, groups the detailed filters, and centers its writing/reading surface. Organization, writing options, references and existing subsections can fold away. Invalid fields open their containing panels. Removed subsections retain their data for undo but skip native validation while marked for deletion. Plain-text mode hides Markdown formatting controls. Sections retain their ordering, deletion, reference and image behavior.

The country drawer is wider on desktop. Empty fact categories and undated placeholders are omitted. Equally ranked figures and conflicts remain; available area, government and demographic observation dates remain visible. The later refinement removes the Sources disclosure, individual statement links and the population year from the drawer at the user’s request. Snapshot provenance, dates and references remain in the bundled data and country-facts documentation. Wikipedia stays visible. Overview-note selection remains in Notes; saved country entries remain accessible from the drawer. Empty article sections are omitted while disabled-source notices, stale results, failures and retry controls remain available.

The player keeps its existing shell-owned iframe and validation. Desktop Map places it on the left, opposite the country drawer. Wide non-map pages reserve a column for playback; smaller pages reserve bottom space. Minimize/restore icons follow the existing playback state. Map drawing, country data, news fetching, lazy video loading and retained Map/Journal workspaces keep their existing implementation.

## Manual review

No tests or browser checks were added or run, as requested. Source changes were reviewed and whitespace checked. The visual result and browser interactions require your review.

Start from the project folder:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000 and hard-refresh with Ctrl+F5 so the new stylesheet and JavaScript load.

- Settings: all four section links work, the active section is underlined, theme previews select dark/light/brown, and home/label choices persist when returning to Map. Expand source feed controls, save a toggle, and inspect its retained health. Disabled channels remain locked. Export downloads; import still previews before confirmation.
- Journal: search is visible; collections and detailed filters expand. New/edit has a centered title and writing area. Formatting, Preview, plain text, organization, references, tags, section add/reorder/remove/undo and saving remain usable. An invalid reference should expose its panel. Save an entry with an empty section marked for removal. Reading, source/video links and image upload remain accessible.
- Country: Overview omits empty categories and missing-date labels. Population has no date beneath it; multiple figures remain and Wikipedia works. The removed source disclosure and Source buttons should be absent. Notes still offers choosing/creating an overview and viewing saved entries. Articles and Videos have clearer titles and compact save/play actions; empty, stale and failed results remain understandable.
- Player/navigation: play, minimize, restore, replace and close. Move Map → Journal → Settings → Map: the same video should continue and your map position, drawer content and Journal draft should resume. Check that the wider drawer still leaves the selected country visible.
- Appearance: try all three themes at desktop size and about 390px wide. Look for readable contrast, wrapping, accessible controls, horizontal overflow and player/drawer overlap. On narrow screens, collections fold away and Settings cards become one column.

## Typography and control refinement

- Replaced the original icon paths with the original outline SVGs from **Heroicons 2.2.0**, plus its solid heart for the map. Only a small subset is bundled; the MIT license remains in `static/vendor/heroicons/LICENSE`. No runtime package, account, API key, CDN or visible attribution is needed.
- Bundled **Inter 4.1** and **Roboto** variable fonts, including italics, under `static/vendor/fonts/`. Their original SIL Open Font Licenses and pinned provenance/hashes are included. Desktop/tablet interface text uses Inter; widths up to 46rem use Roboto. The fallback stack includes system-ui, Apple system fonts, Segoe UI, Helvetica Neue, Arial, Noto Sans, Liberation Sans and the system sans-serif. The existing map glyph pipeline remains separate from CSS interface fonts.
- Increased small text sizes, removed header icons and centered the header's outer links within a 76rem content width. Settings cards stretch to match the tallest card in their grid row. Every page reserves the root scrollbar gutter.
- Enlarged flags. Country favorites use an outline heart or a filled red heart with an accessible pressed state. Favorited countries show the bundled red heart on the map; favorites remain the same shared database records.
- `static/js/ui_controls.js` enhances native selectors and checkbox labels. Dropdowns have themed options, keyboard navigation, search for country/long option lists, and removable selection chips for multiple countries. Country selectors in filters, entries, presets, home-country preferences, Google News diagnostics and favorite jumps are searchable. Search normalizes case and accents and also matches ISO codes.
- Native selects/checkboxes retain their names, values, validation and form associations. There is no custom serialized data model. Dynamically added form rows and asynchronously populated options are enhanced with one scoped observer. Retained pages reuse their enhanced nodes; the floating menu closes on page cleanup. Without JavaScript, the original form controls remain usable.

Additional manual review after saving drafts and pressing Ctrl+F5:

1. At desktop and 390px, confirm the fonts, larger text, text-only header and stable width when switching between pages with/without scrollable content. Check that Settings cards on a row share their height in each theme.
2. Open Journal filters, type `romania` in Countries, choose Romania plus another country, remove a chip, and apply. Repeat in entry tags, Settings home country, source diagnostics, and newly added preset rows. Selections should save exactly as before. Try keyboard arrows, Enter/Space, Escape and Tab; invalid required selectors should expose their error and allow correction.
3. Favorite a country: the outline becomes filled red and a red map heart appears. Unfavorite removes both. Reload and switch themes to check saved state. Clicking the map heart should select that country.
4. Toggle map labels, Journal flags and source choices; controls should look pressed when enabled and subdued when disabled. Source choices still require Save; locked channels stay disabled. The import confirmation remains required.
5. Return Map → Journal → Settings → Map with a video playing and an unsaved entry. Position, draft country selections and playback should resume without duplicate selectors or menus. On phones, opening/searching a menu with the keyboard should keep the menu reachable.

No automated tests or browser sessions were added or run for this refinement; manual verification remains with the user. No migrations or Python requirements changed.
