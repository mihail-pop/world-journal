# Journal statistics

Open **Journal → Statistics** (`/journal/statistics/`). Statistics covers the entire Journal regardless of the list's current filters. There is no search/filter panel or New entry button on this page. Counts are calculated from SQLite; no remote services or chart dependency are involved.

Summary counts cover all entries, favorites, pinned entries, entries without an event date, and entries without country tags. Type, collection and country breakdowns link to matching Journal lists. Main entries count once; subsections are not separate entries. An entry tagged with two countries counts under each country but once in the overall total.

The timeline groups entries by the month they were saved, using the application's time zone, newest first, with 50 nonempty months per page. Entries without event dates are included. Filters and event-date choices remain available on the Journal list. Comparison bars are relative to the largest visible count in each panel. No full entry bodies or attachments are read for aggregates.

## Manual checks

1. Filter the Journal, then open Statistics. All entries should equal the complete Journal total, and there should be no search/filter panel or New entry button.
2. Click type, collection, country, and timeline counts. Their Journal result counts should match the clicked number.
3. Tag one entry with two countries. It counts once overall and under both countries.
4. Check an empty Journal, timeline pagination when applicable, themes, and a narrow window.

No tests or browser checks were run for this change, at the user's request.
