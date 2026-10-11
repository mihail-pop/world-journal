# Journal implementation

One shared journal, with optional collections for grouping entries and ordered subsections inside each entry. No accounts or ownership fields are involved.

## Stored structure

- `countries.Country`: ISO alpha-2 primary key and display name. A frozen migration seeds the 238 bundled identities. Map geometry remains in the existing JSON files. Renaming a country does not change its identity or journal relationships.
- `journal.Collection`: UUID, unique name, description, ordering position, creation/update times. An entry belongs to zero or one collection. Deleting a collection moves its entries to Unfiled rather than deleting research.
- `journal.Entry`: UUID, title, unbounded text body, explicit body format, entry type (note/article/bookmark/YouTube), source URL/name/publication timestamp, optional validated YouTube ID and integer start seconds, optional event date, favorite/pinned flags, creation/update timestamps, collection foreign key, and many-to-many country associations.
- `journal.EntrySection`: UUID, parent entry, position, independent title/body/body format/type and reference fields, creation/update times. The main body remains on Entry; adding/removing subsections does not change its identity. Equal positions have stable creation-time/UUID tie breakers, allowing inexpensive portable reordering without temporary uniqueness violations.
- `journal.Attachment`: UUID, owning entry, optional subsection, local file path, original display filename, caption, detected MIME type, byte size, dimensions, position and creation time. Deleting a subsection preserves its images on the main entry. Confirmed image/entry deletion removes files after the database transaction commits.

These are ordinary related tables, not an opaque editor JSON document. Text is stored as source, not trusted HTML. UUIDs keep links stable; related rows keep an entry from becoming one enormous record. Future features use additive Django migrations. A five-year guarantee cannot come from freezing the initial schema.

Date/type/collection/section-order indexes cover ordinary filtering. Lists are paginated to 30 entries and render a bounded 1,600-character Markdown excerpt rather than loading the full document. The preview has a fixed maximum height. Search is isolated in `journal/query.py` so SQLite FTS can replace substring search later without changing stored research.

## Editing and display

Entries and subsections always use Markdown, including existing entries that previously selected plain text. The legacy body-format field remains in the database and backup format for compatibility, but is no longer an editor option. Markdown supports headings, emphasis, lists, quotes, links, code and tables. Raw HTML and remote Markdown images are disabled. Local JPEG/PNG/WebP/GIF uploads are checked by content, limited to 10 MiB and 40 megapixels, and stored under generated filenames in `media/journal/`.

Exact `[[country name]]`, configured name aliases and ISO-code references create map links and add explicit country tags on save. Unknown references remain visible. Markdown code spans/fences do not tag countries. Existing tags stay until explicitly removed; a reference still in the text will add its tag again. Subsection references also contribute to the owning entry's tags.

Event date, source publication time, and creation time are independent. List filters use event date by default, with created date as an alternative; day takes precedence over month/year. Multi-country filtering matches any selected country. Pinned entries are ordered first.

Article/video cards open a prefilled Journal editor. Saving without choosing a collection creates or reuses Articles (including bookmarks), Videos, or Notes. An explicit collection is preserved. Existing Unfiled entries move to the automatic collection when next saved; deleting a collection still preserves entries. Country overview creation also uses Notes. Types are organizational labels and all support the same body, subsections, sources and video references. Mixed research has been removed: migration 0002 converts its existing entries and sections to Notes, and old backups remain importable. Source pages are not scraped. A source link remains stored when its feed item disappears. Videos are structured IDs/timestamps and reuse the persistent shell player. No iframe is created when merely viewing a journal entry.

Direct URL loads and normal form submissions work without HTMX. HTMX navigation swaps only app-content. Subsection movement and formatting toolbar require JavaScript; Add subsection also has a normal form fallback. The Journal header resumes the last screen when returning from another page. Clicking it while already in Journal saves changed edits first and opens the main list at the top; see [Page memory](page-memory.md).

## Autosave and video links

Changed editors save about every 60 seconds without replacing their DOM, text cursor or body. A small status shows unsaved changes, saving, saved or an error. Retained editors continue saving while Map or Settings is visible. Opening another Journal screen flushes changes first and keeps the editor visible if saving fails. Empty untouched editors are not created. Blank titles on a changed draft become Untitled entry/section. Save entry still performs normal validation and opens the saved detail.

The editor allocates a UUID before autosaving; retries update the same entry. The server rebuilds the inline formset initial/extra boundary from owned section IDs. Responses update new section IDs in place, so later autosaves, reordering, explicit saves and removals operate on the same records. Explicit and background saves are serialized. Automatically detected country tags update the selector if the user has not changed it during the request.

Autosave stores partial work and confirms section removals; it is not version history or crash recovery. A before-unload warning protects changes not yet confirmed saved. Browser background timers can be delayed, and failed validation or connections leave edits unsaved. Separate editors in different tabs can still overwrite one another; this small local app has no collaborative editor or merge system.

Raw YouTube URLs and Markdown links become Play cards in previews, excerpts and full entries. Supported watch, short, live, embed and youtu.be links reuse the existing strict ID/timestamp validator. Code blocks and inline code are unchanged. Play creates the existing shell-owned youtube-nocookie iframe; simply displaying an entry creates no iframe and makes no YouTube request. Videos without a usable video ID, including playlist-only links, remain text/links. No dependency or network metadata lookup is added.

## Local setup and manual checks

Use the workspace interpreter:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/journal/. Create a collection and an entry, add/reorder subsections, preview Markdown, tag countries using explicit references, and save. Reopen/edit and use country/type/event-date filters. Save an article/video from the map; its title/source/country should be prefilled. Add a video URL and seconds, then Play on the detail page. Upload a local image into the main entry or a subsection. Check themes, a narrow window, and player continuity through Journal/Map/Settings. Check confirmation screens before deleting data; deleting a collection should preserve its entries.

No new tests were generated, no test suite was run, and no browser acceptance was performed for this implementation, at the user's request. Schema generation/application are setup steps, not a claim of runtime verification.

## Still deferred

Crash recovery/version history, nested collections, cross-entry backlinks, attachment caption editing/thumbnail generation, and advanced full-text search. [Journal statistics](journal-statistics.md) provides counts and links back to filtered entries. Portable export/import is available in Settings; see [Backups](backups.md). Manually back up SQLite and the media directory together while the server is stopped for an exact copy. The dependency pins and source model do not require a frontend build or background worker.
