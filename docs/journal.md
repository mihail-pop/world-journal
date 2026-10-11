# Journal implementation

One shared journal, with optional collections for grouping entries and ordered subsections inside each entry. No accounts or ownership fields are involved.

## Stored structure

- `countries.Country`: ISO alpha-2 primary key and display name. A frozen migration seeds the 238 bundled identities. Map geometry remains in the existing JSON files. Renaming a country does not change its identity or journal relationships.
- `journal.Collection`: UUID, unique name, description, ordering position, creation/update times. An entry belongs to zero or one collection. Deleting a collection moves its entries to Unfiled rather than deleting research.
- `journal.Entry`: UUID, title, unbounded text body, explicit body format, entry type (note/article/bookmark/YouTube/mixed), source URL/name/publication timestamp, optional validated YouTube ID and integer start seconds, optional event date, favorite/pinned flags, creation/update timestamps, collection foreign key, and many-to-many country associations.
- `journal.EntrySection`: UUID, parent entry, position, independent title/body/body format/type and reference fields, creation/update times. The main body remains on Entry; adding/removing subsections does not change its identity. Equal positions have stable creation-time/UUID tie breakers, allowing inexpensive portable reordering without temporary uniqueness violations.
- `journal.Attachment`: UUID, owning entry, optional subsection, local file path, original display filename, caption, detected MIME type, byte size, dimensions, position and creation time. Deleting a subsection preserves its images on the main entry. Confirmed image/entry deletion removes files after the database transaction commits.

These are ordinary related tables, not an opaque editor JSON document. Text is stored as source, not trusted HTML. UUIDs keep links stable; related rows keep an entry from becoming one enormous record. Future features use additive Django migrations. A five-year guarantee cannot come from freezing the initial schema.

Date/type/collection/section-order indexes cover ordinary filtering. Lists are paginated to 30 entries and read a short body excerpt rather than the full document. Search is isolated in `journal/query.py` so SQLite FTS can replace substring search later without changing stored research.

## Editing and display

Entries and subsections support Markdown or plain text. Markdown supports headings, emphasis, lists, quotes, links, code and tables. Raw HTML and remote Markdown images are disabled. Local JPEG/PNG/WebP/GIF uploads are checked by content, limited to 10 MiB and 40 megapixels, and stored under generated filenames in `media/journal/`.

Exact `[[country name]]`, configured name aliases and ISO-code references create map links and add explicit country tags on save. Unknown references remain visible. Markdown code spans/fences do not tag countries. Existing tags stay until explicitly removed; a reference still in the text will add its tag again. Subsection references also contribute to the owning entry's tags.

Event date, source publication time, and creation time are independent. List filters use event date by default, with created date as an alternative; day takes precedence over month/year. Multi-country filtering matches any selected country. Pinned entries are ordered first.

Article/video cards open a prefilled Journal editor. Saving requires an explicit form submission; source pages are not scraped. A source link remains stored when its feed item disappears. Videos are structured IDs/timestamps and reuse the persistent shell player. No iframe is created when merely viewing a journal entry.

Direct URL loads and normal form submissions work without HTMX. HTMX navigation swaps only app-content. Subsection movement and formatting toolbar require JavaScript; Add subsection also has a normal form fallback. The Journal header now resumes the last screen and preserves an unfinished editor across section switches in the current tab; see [Page memory](page-memory.md). There is no autosave or crash recovery yet: save before refresh, full navigation, closing the tab or opening another Journal screen.

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

Autosave/recovery, nested collections, cross-entry backlinks, attachment caption editing/thumbnail generation, and advanced full-text search. [Journal statistics](journal-statistics.md) provides counts and links back to filtered entries. Portable export/import is available in Settings; see [Backups](backups.md). Manually back up SQLite and the media directory together while the server is stopped for an exact copy. The dependency pins and source model do not require a frontend build or background worker.
