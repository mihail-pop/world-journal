# News-source settings

Open **Settings → Manage news sources** (`/settings/news/`). Preferences are
shared by this local installation and stored in SQLite. No accounts or new
dependencies are required.

## Choices and freshness

- Google News, regional publishers, their individual feeds, and YouTube channels
  have separate on/off choices. Changes save immediately without a page reload.
  Writes contain only the changed control; failed saves restore its previous
  value and show an error. Manual saving remains for JavaScript-disabled browsers.
- Switching off a publisher pauses its feeds without forgetting their individual
  choices. Re-enabling it restores those choices.
- Al Arabiya and its five feeds have been removed from the active configuration.
  The four YouTube candidate IDs were replaced with verified working channels
  on October 11, 2026 and can now be enabled.
- Background refresh runs every 5–120 minutes (30 by default). Each feed's own
  fetch/check timestamp determines when it is due. The previous default of 15
  minutes is upgraded to 30 by the migration; other saved intervals are retained.
- Changing preferences does not remove cached feeds, journal items, or the playing
  video. Visible drawer results update as refreshed feeds become available.

The curated registry remains authoritative for built-in endpoints and metadata.
Custom sources live in SQLite and join the same effective registry.
The preferences can disable reviewed records, but
cannot enable an unavailable registry record. Disabled records are skipped before
fetching. Video feeds are warmed in the background; thumbnails and playback remain
lazy on the Map page. See [Background news cache](news-background.md).

## Health and manual refresh

Health on this page reads the retained feed cache. The first application page
request starts the background warmer, without waiting for publishers.
Google News health is specific to the selected country. Regional and YouTube
health covers the whole feed, so its entry count can differ from country matches.

**Refresh now** checks one saved, enabled endpoint. It bypasses normal freshness
and failure backoff for that request, but keeps existing bounded fetching,
conditional requests, identity validation, and stale fallback. A successful empty
feed is different from a failed refresh. Choices save directly. Changing the
Google health country reloads Sources with that country's cache details.

The last successful check includes HTTP 304 responses. Registry review dates are
separate historical audit dates. Health is not a permanent event log: when the
underlying cache expires, the page reports no retained check. A failed refresh
retains prior usable results where available.

After a failed refresh, **Feed details → Failure reason** distinguishes publisher
HTTP errors (including 403, 404 and 429), connection/time limits, invalid feed
responses and channel identity mismatches. Old cache records may have only the
generic warning until another refresh. YouTube rows also expose their derived
Atom feed link.

## Custom feeds and channels

Use **Your sources → Add a source**. Choose Article RSS / Atom or YouTube channel,
paste the location and optionally supply a name. **Add and check** makes one
bounded live check, detects the format and retains normalized entries immediately.
No API key, dependency or special publisher parser is required.

- Article feeds support feedparser's RSS and Atom variants, including RSS 2.0,
  RSS 1.0/RDF and Atom 1.0. Relative links resolve against the fetched address.
  Article links can use HTTP or HTTPS; feed downloads require HTTPS. Public HTTPS
  redirects retain existing DNS, size, timeout and redirect checks at every hop.
- YouTube accepts a UC channel ID, `/channel/…` link, channel Atom URL, channel
  `@handle` link or bare `@handle`. Public channel metadata resolves handles; the
  resulting Atom channel identity is then verified. If metadata is unavailable,
  use a channel ID or feed URL. Individual videos and playlists are not channels.
- Successful empty feeds are shown as empty, not broken. Failed first checks
  remain visible with a reason and stay paused until **Check again** succeeds.
  Later failed checks retain usable cache. Duplicate URLs/channel IDs are reported.
- Verified sources join background refresh. Articles appear under Regional
  reporting and channels under Videos. Both can contribute to all countries,
  subject to existing country matching and limits. Aliases remain English/reviewed
  terms; no automatic translation or full article scraping is added.
- Removal keeps saved journal entries. Configurations and check metadata join
  version 3 backups; feed cache remains excluded. Version 1/2 backups still import.

## Setup and manual checks

Use the workspace virtual environment:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` and reload with Ctrl+F5 after updating static files.

1. Open source settings. Al Arabiya is absent. Sources and saved choices appear
   immediately while background preparation proceeds. Reopening the page shows
   the latest retained health.
2. Turn Google News off. Wait for Saved, then open Articles: Google shows a
   switched-off message while enabled regional coverage remains available.
3. Disable a regional publisher, then enable it again. Its individual
   feed checkbox choices should be retained. Unavailable channels remain locked.
4. Save a freshness value, revisit the page, and confirm it persists. Values
   outside 5–120 should show a validation message.
5. Refresh one enabled source. Its attempt time and cache status update; a remote
   failure shows a warning and keeps prior usable cached entries. Google checks
   use the chosen country.
6. Try the page in all themes and a narrow window. Navigate between Map, Journal,
   and Settings while a video plays; the shell player should stay intact.
7. Add an RSS/Atom feed and a YouTube channel that are not built-in. Check their
   name, detected format and cache status. Open a country mentioned in an item
   and confirm attribution. An invalid feed should show its reason and stay paused.
8. Check again/remove a failed source; try adding a duplicate. Toggle choices
   quickly, change the interval and revisit Sources: values should persist.
   Stop the server before toggling to verify the previous choice is restored.
9. Export/import on an empty installation: custom sources and choices should
   return. Re-importing should not create duplicates.

Additional manual checks for first-load preparation, priority, persistence and
automatic refresh are in [Background news cache](news-background.md). Automated
tests and browser acceptance were intentionally left to the user.
