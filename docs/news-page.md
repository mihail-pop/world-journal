# General News page

Open **News** in the header or `/news/`. Articles are the default tab; Videos has
its own channel and sorting controls. This page reads the same SQLite feed cache
as country drawers, without requiring country mentions in titles or summaries.
There are no new dependencies, account requirements or migrations for this page.

## Articles

- Google coverage defaults to the World headlines RSS feed, in English using the
  US edition. This is one extra background feed, rather than a combination of
  238 country searches. It retains up to 100 supplied headlines.
- A searchable country selector reuses that country's existing Google cache.
  Country coverage applies only to Google; regional feeds remain general news.
- Source choices include All articles, Google News, Regional publishers and each
  enabled regional/custom publisher. Publisher and per-feed switches still apply.
- Top stories keeps Google feed order first and balances recent regional items
  across publishers. Newest sorts all selected items by publication timestamp.
  No article click count, numerical relevance score or popularity is invented.
- Past 24 hours, Past 7 days and All recent feed items filter publication dates
  locally. Undated items appear only in All recent feed items. Feeds supply a
  bounded current snapshot, so these views are not full historical archives or
  a ranking of every story published during the week.
- Deduplication collapses identical links or publisher/title pairs, preserving
  different publishers' reporting. Full article bodies are not downloaded.

Google explains its algorithmic news ordering at
https://www.google.com/intl/en_us/search/howsearchworks/how-news-works/.
The World endpoint used here is
`https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US%3Aen`.
It returned a valid World feed during the implementation metadata inspection.
Google publishes no stable feed ranking/query API contract.

## Videos

All enabled channels, including custom channels, contribute their recent uploads
without country matching. Newest orders by publication time. Most viewed orders
by optional `media:statistics/@views` values from each channel's Atom feed.
Counts are snapshots from the last successful refresh, not live playback stats.
This is a comparison of recent feed videos, not YouTube's global trending chart.
Unknown counts go after known counts and then sort by date; zero is a valid count.
Existing caches without the new view field are upgraded once in the background
when Videos is first opened. A failed upgrade respects ordinary retry backoff.

The Al Jazeera feed supplied the view-count field during the metadata inspection.
Parsing still validates channel identity and video IDs and derives all video URLs.
Thumbnails load only on the visible Videos page. An iframe is created only by
Play, using the existing persistent youtube-nocookie player. Save opens the same
Journal entry form as country news; general items have no automatic country tag.

## Cache, navigation and failures

The World feed joins the existing bounded queue, shared refresh progress and
Refresh now action. It shares the 12-hour default plus 1–30 minute offset, Google
request pacing, conditional requests, stale fallback and Google-wide cooldown.
First preparation retains the original short spacing between downloads.
Disabled sources are excluded before fetching and rendering.

Initial page rendering is cache-only. Missing/due feeds are promoted without
waiting for publishers. Results poll every five seconds during preparation and
30 seconds afterward, only while this page is visible. Version comparisons avoid
repeating unchanged rendered HTML. Responses belong to the page's own filter
parameters; outgoing requests are aborted and late responses are discarded.
Open summaries are retained when results update. Sources with failed or stale
results have a collapsed notice list; successful sibling feeds remain available.

Filters, tabs and pagination use normal GET URLs enhanced by HTMX. Without
JavaScript, Apply and normal navigation still work. News keeps its current nodes,
filters and scroll when navigating to another main page, like Journal. Clicking
News in the header while already on News returns to the main Articles screen.
Playback and the retained Map remain outside these results updates.

## Manual checks

Restart the local server, then reload with Ctrl+F5:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

1. Open News: Articles should show World headlines and general regional articles,
   including items whose titles contain no country name. Missing items should
   appear as background preparation completes, without a full-page refresh.
2. Choose Google News, a country, a regional publisher, each date range and each
   sort. Check URL/back/forward behavior and rapid filter changes. Country choices
   should be searchable and only one dropdown should be visible per field.
3. Open Videos and choose Most viewed: available counts should descend. Old
   caches should populate counts after their one-time refresh. Filters apply
   only to the recent uploads supplied by enabled channels.
4. Play, minimize, restore and close a video. Navigate News → Journal → Settings
   → Map. The player should retain its iframe until closed or another video is
   played. Returning to Map should retain one map and its previous selection.
5. Scroll News, navigate away and return using the header: state should survive.
   Clicking News while already on News should return to default Articles at top.
6. Save an article/video to Journal. Check source, URL/video and publication date.
   General items should not receive a guessed country tag; a country-specific
   Google result should carry the chosen country.
7. Disable a publisher/channel/Google in Sources and revisit News. Disabled items
   should disappear. Refresh now should include World headlines in progress.
8. Check dark/light/brown themes, desktop and 390px layouts, pagination, and
   partial/total feed failure. Cached items should remain available during refresh.

No automated tests, system checks or browser acceptance were run. Live requests
were limited to inspecting one World feed and one channel's available metadata;
no fabricated data was written to the application's database.
