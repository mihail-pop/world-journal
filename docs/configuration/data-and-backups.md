# Data and Backups

World Journal keeps personal data on the machine running the app. There is no cloud copy to restore from, so backups matter.

## Where Data Is Stored

- `db.sqlite3` contains journal entries, collections, country relationships, favorites, presets, source choices, the news archive and custom territory edits. Docker stores this file under `runtime/`.
- `media/` contains uploaded journal images.
- Browser preferences such as the theme, home country, map type, player position and retained page state are stored in that browser.
- `world_journal_cache` is a table inside SQLite used for feed snapshots. Cached news can be downloaded again and does not need to be treated as permanent data.

## Portable Backup

Open **Settings > Backup** and export a ZIP archive. The archive includes the journal, attachments, collections, country relationships, favorites, map presets, source choices and custom territory details.

Import always starts with a preview. Review what will be added, kept or reused before confirming the write.

> **Note:** Feed cache and the rolling news archive are temporary research aids. Explicit Journal saves are the permanent record.

## Manual Backup

For a complete native-install copy:

1. Stop the Django server.
2. Copy `db.sqlite3` and the entire `media/` folder together.
3. Store both copies somewhere outside the project folder.
4. Start the server again.

Copying the database while the app is actively writing can produce an inconsistent backup, so stop the server first.

For Docker, stop the container with `docker compose down`, then copy `runtime/db.sqlite3` and `media/`. Start it again with `docker compose up -d`.
