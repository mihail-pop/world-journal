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
- Background refresh offers 6, 8, 10 or 12 hours (12 by default). Each feed's own
  successful-check timestamp determines when it is due, plus a stable 1–30 minute
  offset that changes after each successful check. This extends the refresh
  interval, not the spacing between downloads. Missing feeds load immediately.
  Migration 0005 upgrades saved minute-based intervals to 12 hours; old backups
  receive the same upgrade on import.
- Changing preferences does not remove cached feeds, journal items, or the playing
  video. Visible drawer results update as refreshed feeds become available.

The curated registry remains authoritative for built-in endpoints and metadata.
Custom sources live in SQLite and join the same effective registry.
The preferences can disable reviewed records, but
cannot enable an unavailable registry record. Disabled records are skipped before
fetching. Video feeds are warmed in the background; thumbnails and playback remain
lazy on the Map page. See [Background news cache](news-background.md).

## Shared refresh card

The top row has three small cards: Background refresh, Google News and Feed cache.
Feed cache shows real completed/total queue jobs, the active source/country names
and a progress bar. Status polls every two seconds while busy and every 15 seconds
while idle, only on the Sources page; hidden tabs pause polling. Finishing shows
Done/cache ready or a count of unavailable feeds. Failure details live together
in that card. Individual cards no longer repeat cache times, counts or refresh
buttons. Source links and publisher notes remain available.

**Refresh now** queues all enabled regional feeds, channel feeds and country
Google feeds without blocking the page. It bypasses freshness/backoff but keeps
conditional requests, the bounded worker pool, Google pacing and stale fallback.
Google-wide rate-limit pauses apply even to manual refreshes. A 429 pauses all
country queries; the pause honors Retry-After if supplied. Other feed failures
retry after 30 minutes, then 1, 2, 4, 8 and 12 hours, capped at 12 hours unless a
publisher requests a longer wait. Successful checks reset the failure count.
Repeated clicks during a manual sweep do not create another sweep. Sources that
are disabled before dispatch are skipped. Existing in-flight checks count toward
the sweep and are not duplicated. No useful cache is deleted to create progress.
The button is disabled while refreshing. Progress is process-local, and resets
after a Django restart; retained feed snapshots remain in SQLite.

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
  version 4 backups; feed cache remains excluded. Version 1–3 backups still import.
- Each custom card has an accessible X. Removing an article publisher removes
  its associated additional feeds. In an article card, **Feed details → Add feed**
  adds a second feed under that publisher with its own label, format, validation,
  cache and switch. Extra feeds have an X of their own. Turning the publisher off
  pauses them all without forgetting feed switches. A failed first check remains
  visible with Check again; unrelated feeds continue working. Existing custom
  sources retain their identities and original feed through migration.

## Setup and manual checks

Use the workspace virtual environment:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` and reload with Ctrl+F5 after updating static files.

1. Open source settings. Al Arabiya is absent. Sources and saved choices appear
   immediately while the shared card shows background preparation.
2. Turn Google News off. Wait for Saved, then open Articles: Google shows a
   switched-off message while enabled regional coverage remains available.
3. Disable a regional publisher, then enable it again. Its individual
   feed checkbox choices should be retained. Unavailable channels remain locked.
4. Confirm the interval defaults to Every 12 hours. Choose 6, 8 or 10 hours,
   wait for Saved, revisit and confirm it persists. Restore 12 hours afterward.
5. Press the shared Refresh now. Progress should count completed feeds, show
   active sources, then finish. Failures should appear together; cached country
   results and any playing video should remain available. Navigate away/back
   during a sweep and confirm progress resumes from the server.
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
10. Add an extra RSS feed inside an article card's Feed details. It should appear
    in that card rather than a second publisher card. Check its individual switch,
    publisher switch, failure behavior and X. The card X removes the group.

Additional manual checks for first-load preparation, priority, persistence and
automatic refresh are in [Background news cache](news-background.md). Automated
tests and browser acceptance were intentionally left to the user.
