# Database Schema

World Journal uses Django's ORM with one local SQLite database. The schema keeps permanent personal research separate from temporary feed cache while allowing countries to connect the rest of the app.

## Countries

`Country` stores the stable two-character identity used by routes and relationships. The original 238 entries use ISO-backed data. The 14 additional Natural Earth areas use reviewed local `X` keys and set `is_custom`.

Key related models are:

- **`TerritoryDetails`** stores local fact and name overrides for custom territories.
- **`CountryFavorite`** stores shared favorites.
- **`CountrySelection`** counts country selections for Google News refresh ordering.
- **`MapPreset`** stores each named color preset.
- **`PresetCountry`** assigns a color to a country inside a preset.
- **`PresetColorGroup`** stores optional group titles used by the legend.
- **`CountryProfile`** connects a country Overview note to the Journal.

Names are display data, not relationship keys. Editing a custom territory name does not replace its country row or break existing tags.

## App Settings

`AppSettings` stores the shared Preferences, including the theme, font, home country, map display options and active color preset.

## Journal

`ResearchContent` contains the fields shared by entries and subsections. Both use JSON for rich-text documents and store structured article and video references.

- **`Collection`** organizes entries.
- **`Entry`** stores the main record, UUID, type, dates, flags and country relationships.
- **`EntrySection`** stores ordered child sections.
- **`Attachment`** stores metadata for uploaded local images.

Uploaded files live under `media/`; the database stores their relationships and metadata. Signals handle deliberate cleanup when records are removed.

## News

Feed snapshots use Django's `world_journal_cache` database table. The durable news models are used for preferences, custom sources and bounded history:

- **`ArchivedNews`** stores normalized article or video metadata for the rolling archive.
- **`ArchivedNewsSource`** connects archived items to their source identity.
- **`ArchivedNewsCountry`** records country matches.
- **`ArchiveUsage`** tracks the estimated archive size and item count.
- **`FeedState`** stores feed metadata and archive progress.
- **`FeedSchedule`** stores refresh timing and the current Google News sweep.
- **`SourcePreference`** stores enabled or disabled source choices.
- **`NewsPreferences`** stores the refresh interval, archive budget and Google News request gaps.
- **`CustomSource`** stores user-added feeds and channels.

The archive keeps metadata within the selected budget of 500 MB, 1 GB or 2 GB, with 2 GB as the default and a 3 million item safety cap.

## Backups and Migrations

Django migrations are the source of truth for schema changes. Country catalog migrations also seed stable country rows that other records reference.

Portable backups contain saved personal data and media. The current format is 12, and imports support formats 1 through 12.

When adding or changing a stored model, review all of these areas together:

1. the Django model and migration;
2. portable export and import mappings;
3. merge and conflict behavior;
4. invalidation of retained browser views;
5. documentation for any user-visible data.
