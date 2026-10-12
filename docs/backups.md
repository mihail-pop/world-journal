# Backup and import

Open **Settings → Manage backups** (`/settings/backups/`). No additional
dependencies, accounts, or background service are needed.

## Portable export

Download backup ZIP after saving open editors. The archive contains a UTF-8
`manifest.json` identifying format `world-journal-backup`, version `4`, export
time, record datasets, and SHA-256 image checksums. Image files use generated
archive paths under `media/`; original display filenames remain in metadata.

Included data:

- Journal collections, entries, ordered subsections, country tags, event dates,
  source links, video IDs/timestamps, favorite/pinned flags, and original dates.
- Local image bytes, captions, subsection links, names, dimensions, and ordering.
- Country favorites, map presets/colors, ordered group titles, the shared active preset, and country
  overview-to-journal links.
- Shared source choices, refresh interval and custom RSS/YouTube sources.

Country identities, map geometry, facts, and built-in source definitions remain bundled
application configuration. They are not overwritten by an archive. Feed cache,
rolling feed history, sessions, secrets, and browser preferences are excluded.
Articles/videos explicitly saved to Journal are permanent backup data. Export explicitly fails
when a referenced image is missing or has changed size rather than silently
omitting it. Export uses temporary storage, which is closed after the download.

## Preview and confirmation

Upload an application-generated ZIP, review the Add / Keep existing / Reuse
counts, then tick the confirmation checkbox and confirm. Preview validates the
format/version, field types, country codes, parent relationships, paths, image
content, dimensions, size, and checksums. Preview writes only a private temporary
upload and session token, not journal records or shared preferences.

The first import policy is a merge:

- Existing UUIDs and other primary identities are kept unchanged.
- Collections and presets with an existing name reuse the existing container;
  its description and settings remain unchanged. New entries can use a reused
  collection.
- Subsections and images import only for entries being added. Existing entry
  content is never augmented from an older backup. An attachment whose subsection
  conflicts is also skipped.
- Colors and titled color groups import only for new presets. Existing preset colors and group titles remain unchanged.
- Existing country favorites, overview links, source choices, news preferences,
  and active-preset state are kept. A conflicting one-entry-per-country overview
  association is skipped.

Conflict counts are recalculated at confirmation. Database writes run in one
transaction. Imported files get new local storage names, and files created during
a failed database import are removed where storage permits. Original creation,
update, and publication dates are retained. Archives are never extracted onto
the host filesystem and never replace the database file.

A truly empty installation can restore every record. Re-importing a backup into
its originating database adds no duplicate entries or images. This merge is not
an undo of edits to records that still exist: use an exact local copy for that.

Temporary previews live in `.backup-imports/`, outside publicly served media and
ignored by Git. Confirming, discarding, or replacing a preview removes its file.
Expired files are removed on staging-directory access after 24 hours. A preview
belongs to the browser session that uploaded it. Normal and HTMX forms work;
HTMX swaps only page content so the persistent player remains mounted.

Defaults: 512 MiB for the ZIP and its expanded content; 32 MiB for the manifest;
100,000 records; existing image upload size and 40-megapixel limits. Configure
`BACKUP_MAX_BYTES` if a legitimate archive grows past the default. Version 2 adds the `preset_groups` dataset without changing the version 1 fields.
The importer accepts version 1 archives, which have no titled group metadata;
the preset editor and legend derive untitled groups from their country colors.
Version 3 adds custom sources, including detected format, channel identity and
check metadata. Version 1 and 2 archives remain readable. Sources already present
at the same URL are reused without replacing their configuration or choices.
Version 4 adds parent links for additional custom article feeds. Version 3 sources
import as independent publishers/channels, preserving their identities. Versions
1–3 remain readable; older app versions cannot read version 4 exports.

## Exact manual backup

1. Stop the server with Ctrl+C.
2. Copy `db.sqlite3` and the entire `media` directory together to a separate backup
   location. If media does not exist yet, there are no local images to copy.
3. Restart using the command below.

To restore that copy, stop the server first and retain a copy of the current
database/media before replacing them. Use the matching application version and
apply its migrations when upgrading. A portable archive or exact copy contains
personal research; store it somewhere trusted. A server exposed beyond localhost
also exposes exports and write actions because the application has no accounts.

## Manual acceptance

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/`, reload static files with Ctrl+F5, then:

1. Download an archive containing an entry with country tags, a subsection, an
   image, and a video timestamp. Inspect that the ZIP has a manifest and image.
2. Preview that same archive. Existing records should be skipped or reused; no
   journal content should change. Confirming should add zero duplicate records.
3. Export a disposable entry, then delete that entry through its normal confirmed
   delete screen. Import the saved archive. That entry, its subsections, country
   tags, image, and original dates should return. Existing entries stay unchanged.
4. Discard a preview. No records should be imported. Upload an unrelated ZIP: it
   should show a readable validation error and leave data alone.
5. Check all themes, a narrow window, and player continuity while navigating.

No automated tests were generated or run, and no browser verification was
performed for this step, as requested.
