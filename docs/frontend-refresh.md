# Interface refresh

This pass changes presentation using Django templates, one shared CSS layer (`static/css/ui.css`), reusable inline SVG icons, and the existing JavaScript modules. It adds no dependencies, migrations or frontend build. `APP_CONTEXT.md` is unchanged.

Settings uses direct, HTMX-enabled links for Preferences, Backup, Sources and Information. Source toggles still belong to the shared preferences form; refreshing one feed remains a separate action. Export remains an ordinary download and import retains its preview and explicit confirmation.

The Journal keeps search visible, groups the detailed filters, and centers its writing/reading surface. Organization, writing options, references and existing subsections can fold away. Invalid fields open their containing panels. Removed subsections retain their data for undo but skip native validation while marked for deletion. Plain-text mode hides Markdown formatting controls. Sections retain their ordering, deletion, reference and image behavior.

The country drawer is wider on desktop. Empty fact categories and undated placeholders are omitted. Real observation dates, equally ranked figures, conflicts and statement source links remain. Source methodology, licensing, identity codes and snapshot provenance are retained under **Sources & figure details**. Wikipedia stays visible. Overview-note selection remains in Notes; saved country entries remain accessible from the drawer. Empty article sections are omitted while disabled-source notices, stale results, failures and retry controls remain available.

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
- Country: Overview omits empty categories and missing-date labels. Actual dates and multiple figures remain, Wikipedia works, and the Sources disclosure opens. Notes still offers choosing/creating an overview and viewing saved entries. Articles and Videos have clearer titles and compact save/play actions; empty, stale and failed results remain understandable.
- Player/navigation: play, minimize, restore, replace and close. Move Map → Journal → Settings → Map: the same video should continue and your map position, drawer content and Journal draft should resume. Check that the wider drawer still leaves the selected country visible.
- Appearance: try all three themes at desktop size and about 390px wide. Look for readable contrast, wrapping, accessible controls, horizontal overflow and player/drawer overlap. On narrow screens, collections fold away and Settings cards become one column.
