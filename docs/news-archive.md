# Rolling news history

World Journal retains article/video metadata encountered in successful feed
snapshots for up to **90 days**. This is separate from both the short-lived feed
cache and permanent Journal entries. No complete articles, video files or images
are downloaded into the archive.

## Limits and cleanup

Defaults in `config/settings.py`:

- `NEWS_ARCHIVE_DAYS = 90`
- `NEWS_ARCHIVE_MAX_ITEMS = 50_000`
- `NEWS_ARCHIVE_MAX_BYTES = 100 * 1024 * 1024`
- `NEWS_ARCHIVE_PAGE_SIZE = 20`

The byte limit accounts for UTF-8 metadata plus conservative row/index and
source/country-association overhead. It is an archive budget, not an exact cap
on the whole SQLite file: Journal data, feed cache and SQLite's reusable free
pages are separate. SQLite normally reuses freed pages instead of shrinking its
file immediately.

Cleanup runs at startup/at least hourly while the existing scheduler runs, and
limits are enforced after every changed captured snapshot. Items expire 90 days
after their publication date. Undated items age from their first recorded
encounter; future publication dates cannot extend retention. Repeated sightings
of an existing record do not reset its expiration. If item/byte limits are
reached, oldest items are evicted before newer ones. Retention is therefore
**up to** 90 days, not a promise to retain everything regardless of limits.

Item deletion cascades only to that item's archive source/country associations.
There are no archive-to-Journal foreign keys. Anything explicitly saved in
Journal remains until the user deletes it.

## Collection and identity

The existing background queue captures successful snapshots and seeds existing
cached snapshots when first started. It makes no additional publisher requests
for history and retains the current fetch pacing/refresh interval. An unchanged
successful snapshot is processed once per feed in a running process. Removing
configured jobs removes their process-local stamps.

Articles deduplicate by normalized URL, ignoring fragments and common tracking
parameters. Dated identical title/publisher/timestamp matches also join feed
duplicates such as Google wrapper/direct publisher links; direct publisher links
are preferred when joined. Videos deduplicate by validated video ID. Short
plain-text summaries are capped at 2,000 characters; titles/publisher names are
bounded, and overlong links are skipped rather than truncated.

Google country results keep their existing query-country association. Regional
articles use the existing reviewed title/summary matcher, and videos use the
title-only matcher. Multiple country/source associations share one stored item.
Country identities remain strict bundled ISO codes. Disabled sources are hidden
from archive queries. Removing a custom source deletes its archive associations
and any items no longer belonging to another source, without touching Journal.

The archive can preserve only what the app sees while running. It cannot recover
past editions absent from feeds/cache, and publishers may remove items between
the configured refreshes. RSS feeds and channel feeds are not complete historical
datasets. An empty initial history is expected for many countries.

## Reading history

Map/Countries article and video panels now include **Earlier coverage**. It
starts collapsed when current cards exist and opens automatically when they do
not. The News page also offers Earlier coverage beneath the current results;
its selected source/channel applies to history. Selecting a Google country on
News opens that country's earlier coverage, including regional country matches.
The live News board's date/sort controls continue to describe its live feed items;
history is ordered by publication/first-seen date, newest first.

History loads on demand, 20 items per page, rather than being preloaded for every
country. Country history excludes the cards already shown in that country's
current panel. World history excludes items still in current selected feeds.
Undated cards explicitly say First seen instead of inventing a publication date.
External links, Journal bookmarks and the shell's validated video player are
shared with current coverage; no iframe is created merely by opening history.

Open country history readers survive normal live-feed refreshes, including their
pagination state. Reopening after archive revisions can refresh the reader.
Source preference changes invalidate the reader's source selection. Portable
Journal backups exclude this disposable rolling history just as they exclude
feed cache; permanent Journal saves remain included. A raw SQLite copy retains
the archive as well.

## Installation and manual review

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

The implementation migration was applied locally with system checks skipped,
as requested. Restart the server and press Ctrl+F5 after updating assets.

1. Open a country on Map and Countries, then Articles/Videos → Earlier coverage.
   Initial history may be empty until feeds change or contain additional matches.
2. Check dated older cards, pagination, safe external links, Journal saves and
   playing an archived video in the same persistent player on all three pages.
3. Switch countries/tabs quickly and use Back/Forward; history must stay attached
   to its named country. Opening history must not create a player iframe.
4. Disable a source and check history excludes it; remove a custom source and
   check Journal bookmarks are unaffected.
5. On later refreshes, confirm disappeared feed items remain in earlier coverage
   and repeated items do not accumulate as duplicate cards. Restarting retains
   history. The existing queue remains responsible for automatic pruning.

No test suite, browser session or fabricated feed data was used for this change.
