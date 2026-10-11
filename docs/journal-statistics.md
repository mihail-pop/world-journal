# Journal statistics

Open **Journal → Statistics** (`/journal/statistics/`). Opening statistics from a
filtered Journal list carries those filters forward. Counts are calculated from
the database on request; no feeds, remote services, new dependencies, database
tables, or JavaScript chart library are involved.

## Counts and navigation

- Summary links show matching entries, favorites, pinned entries, entries without
  an event date, and entries without country tags.
- Type counts use the main entry's type. Subsections and source references are
  not separate entries. With a type filter, only that type appears.
- Collection counts include Unfiled. Collection names, country tags, and every
  entry count link to the corresponding filtered Journal list.
- Country counts use saved associations. An entry with several countries counts
  once for each, but once in the overall total. The country breakdown is ordered
  by count, then country name. With a country filter, it shows only selected tags;
  clear that filter to see all countries. This keeps drill-down counts exact even
  when the selected countries are matched with OR semantics.
- Activity groups by day, month (default), or year, newest first. Only nonempty
  periods appear, with 50 periods per page.

The statistics page and Journal share search, collection, country, type, favorite,
pinned, event/created-date, exact day, year, and month filters. They also share the
new **Without event date** and **Without country tags** filters. Exact day takes
precedence over year/month, matching the existing Journal behavior. A date row
keeps other filters; a year row also keeps a month constraint when present.

Event date is the default calendar basis. Entries without one remain in the
overall total and appear in their own summary link. Created date groups saved
timestamps in the application's time zone (currently UTC), and includes entries
without an event date. The Without event date checkbox always describes the
event field, even with a created-date filter.

Search and multiple-country matching use a distinct filtered entry set before
aggregation. Multiple matching subsections or tags cannot inflate the total.
Aggregates do not load full entry bodies, attachments, or image bytes. Comparison
bars are relative to the largest displayed count in each panel; timeline scaling
uses the visible page. Empty journals and empty filtered results have explicit
messages. Counts reflect the last page request; reload after changing data in
another tab. Direct URLs and normal GET forms also work without HTMX.

## Manual checks

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/journal/` and press Ctrl+F5 for updated styling.

1. Open Statistics. Matching entries should equal the unfiltered Journal total.
   Click a type, collection, and country count; the list's result count should
   match the number you clicked. Browser Back should return to statistics.
2. Tag one entry with two countries: it should count once in the total and once
   under each country. Search for text appearing in two subsections of one entry:
   that entry should still count only once.
3. Apply collection/country/favorite filters, then inspect counts and drill-down
   results. Existing filters should stay in the URLs. With several selected
   countries, clicking one country's row narrows to that country.
4. Compare Event date and Created date, and switch day/month/year grouping. An
   entry without an event date should appear in its summary link and the Created
   date timeline. Clicking a date count should open the matching list.
5. Try filters with no results and check the empty message. Check themes, a narrow
   window, direct page loading, and player continuity while navigating.

No automated tests were generated or run, and no browser acceptance was performed
for this step, as requested.
