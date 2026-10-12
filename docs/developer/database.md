# Database Schema

World Journal uses Django's ORM with one local SQLite database. The schema keeps permanent personal research separate from temporary feed cache while allowing countries to connect the rest of the app.

## Countries

`Country` stores the stable two-character identity used by routes and relationships. The original 238 entries use ISO-backed data. The 14 additional Natural Earth areas use reviewed local `X` keys and set `is_custom`.

Key related models are:

- **`TerritoryDetails`** stores local fact and name overrides for custom territories.
- **`CountryFavorite`** stores shared favorites.
- **`MapPreset`** stores each named color preset.
- **`PresetCountry`** assigns a color to a country inside a preset.
- **`PresetColorGroup`** stores optional group titles used by the legend.
- **`MapPersonalState`** records which preset is active.
- **`CountryProfile`** connects a country Overview note to the Journal.

Names are display data, not relationship keys. Editing a custom territory name does not replace its country row or break existing tags.

## Journal

`ResearchContent` contains fields shared by entries and subsections. `Entry` and `EntrySection` inherit from it so both can hold Markdown and structured references without duplicating unrelated tables.

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
- **`SourcePreference`** stores enabled or disabled source choices.
- **`NewsPreferences`** stores shared refresh settings.
- **`CustomSource`** stores user-added feeds and channels.

The archive keeps metadata only. It is limited to 90 days, 50,000 items and an approximate 100 MiB accounted metadata budget.

## Backups and Migrations

Django migrations are the source of truth for schema changes. Country catalog migrations also seed stable country rows that other records reference.

Portable backups use their own versioned format rather than exposing a raw database dump. Backup format 5 includes custom territory edits and remains able to read formats 1 through 4.

When adding or changing a stored model, review all of these areas together:

1. the Django model and migration;
2. portable export and import mappings;
3. merge and conflict behavior;
4. invalidation of retained browser views;
5. documentation for any user-visible data.
